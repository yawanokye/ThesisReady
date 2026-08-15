"""Helpers for enforcing paid chapter actions in ProjectReady AI routes."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional
import os
import uuid

from app.payments.store import claim_entitlement, complete_claim, rollback_claim
from app.payments.internal_access import is_internal_purchase_id, validate_internal_access
from app.access_control import (
    complimentary_action,
    complimentary_token_from_request,
    get_access_policy,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


class PaymentRequiredError(PermissionError):
    """Raised when a paid chapter action is unavailable."""


def credentials_from_headers(headers: Any) -> Dict[str, str]:
    """Read the opaque paid-access credential from FastAPI/Starlette headers."""
    return {
        "purchase_id": str(headers.get("x-projectready-purchase-id") or "").strip(),
        "access_token": str(headers.get("x-projectready-access-token") or "").strip(),
    }


def credentials_from_request(request: Any) -> Dict[str, str]:
    """Read access credentials from a validated internal portal session or headers.

    Restricted module pages use an HttpOnly, signed session cookie.  The main
    application middleware validates that cookie and places the resulting
    credential on ``request.state.internal_portal_session``.  Accepting that
    server-side credential keeps developer access working even when browser
    storage is unavailable, cleared, delayed, or blocked.  Public requests
    continue to use the normal opaque payment headers.
    """
    session = getattr(getattr(request, "state", None), "internal_portal_session", None)
    if isinstance(session, dict):
        purchase_id = str(session.get("purchase_id") or "").strip()
        access_token = str(session.get("access_token") or "").strip()
        if purchase_id and access_token and is_internal_purchase_id(purchase_id):
            return {"purchase_id": purchase_id, "access_token": access_token}
    return credentials_from_headers(getattr(request, "headers", {}))


@contextmanager
def paid_chapter_action(
    *,
    purchase_id: str,
    access_token: str,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    action: str,
    idempotency_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    database_url: str = "",
) -> Iterator[Dict[str, Any]]:
    """Reserve, complete, or refund an included chapter action.

    Use this around the expensive operation. If generation, revision, checking,
    or export raises an exception, the quota is returned automatically.
    """
    if not purchase_id or not access_token:
        raise PaymentRequiredError("Paid chapter access is required for this action.")

    product_area = "all"
    if isinstance(metadata, dict):
        product_area = str(
            metadata.get("product_area")
            or metadata.get("module")
            or "all"
        ).strip() or "all"

    if is_internal_purchase_id(purchase_id):
        try:
            internal = validate_internal_access(
                purchase_id=purchase_id,
                access_token=access_token,
                product_area=product_area,
                project_id=project_id,
                chapter_number=chapter_number,
                action=action,
            )
        except PermissionError as exc:
            raise PaymentRequiredError(str(exc)) from exc
        yield {
            "claimed": False,
            "internal_access": True,
            "access_type": "internal_admin",
            "usage": {},
            "purchase": internal,
        }
        return

    try:
        claim = claim_entitlement(
            purchase_id=purchase_id,
            access_token=access_token,
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            action=action,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            metadata=metadata,
            database_url=database_url or DATABASE_URL,
        )
    except PermissionError as exc:
        raise PaymentRequiredError(str(exc)) from exc

    usage = claim.get("usage") or {}
    usage_id = usage.get("id")
    try:
        yield claim
    except Exception:
        if usage_id and claim.get("claimed"):
            rollback_claim(usage_id, database_url=database_url or DATABASE_URL)
        raise
    else:
        if usage_id and claim.get("claimed"):
            complete_claim(usage_id, database_url=database_url or DATABASE_URL)


def request_access_snapshot(request: Any, product_area: str = "all") -> Dict[str, Any]:
    """Return the request's non-free access signals without consuming anything."""
    policy = get_access_policy()
    credentials = credentials_from_request(request)
    complimentary_token, complimentary_email = complimentary_token_from_request(request)
    return {
        "policy": policy,
        "purchase_id": credentials.get("purchase_id", ""),
        "access_token": credentials.get("access_token", ""),
        "has_paid_or_internal": bool(credentials.get("purchase_id") and credentials.get("access_token")),
        "complimentary_token": complimentary_token,
        "complimentary_email": complimentary_email,
        "has_complimentary": bool(complimentary_token),
        "temporary_open": bool(policy.get("temporary_open")),
        "payment_required": bool(policy.get("payment_required")),
        "free_starter_enabled": bool(policy.get("free_starter_enabled")),
        "product_area": str(product_area or "all"),
    }


@contextmanager
def protected_project_action(
    *,
    request: Any,
    product_area: str,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    action: str,
    requested_pages: int = 0,
    idempotency_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    database_url: str = "",
) -> Iterator[Dict[str, Any]]:
    """Authorize a protected ProjectReady action through open, complimentary, internal, or paid access.

    Background workers pass a pre-authorized claim on request.state. In that case
    this context deliberately does not complete or roll back the claim because the
    worker owns that lifecycle.
    """
    preauthorised = getattr(getattr(request, "state", None), "preauthorized_claim", None)
    if preauthorised:
        yield preauthorised
        return

    snapshot = request_access_snapshot(request, product_area)
    if snapshot["temporary_open"]:
        yield {
            "claimed": False,
            "open_access": True,
            "access_type": "temporary_open",
            "policy": snapshot["policy"],
        }
        return

    if snapshot["has_complimentary"]:
        try:
            with complimentary_action(
                raw_token=snapshot["complimentary_token"],
                supplied_email=snapshot["complimentary_email"],
                product_area=product_area,
                project_id=project_id,
                chapter_number=chapter_number,
                action=action,
                requested_pages=requested_pages,
                idempotency_key=idempotency_key or str(uuid.uuid4()),
                metadata=metadata,
            ) as claim:
                yield claim
                return
        except PermissionError as exc:
            raise PaymentRequiredError(str(exc)) from exc

    with paid_chapter_action(
        purchase_id=snapshot["purchase_id"],
        access_token=snapshot["access_token"],
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        action=action,
        idempotency_key=idempotency_key,
        metadata=metadata,
        database_url=database_url,
    ) as claim:
        yield claim
