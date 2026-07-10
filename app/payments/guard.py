"""Helpers for enforcing paid chapter actions in ProjectReady AI routes."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional
import os
import uuid

from app.payments.store import claim_entitlement, complete_claim, rollback_claim
from app.payments.internal_access import is_internal_purchase_id, validate_internal_access

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


class PaymentRequiredError(PermissionError):
    """Raised when a paid chapter action is unavailable."""


def credentials_from_headers(headers: Any) -> Dict[str, str]:
    """Read the opaque paid-access credential from FastAPI/Starlette headers."""
    return {
        "purchase_id": str(headers.get("x-projectready-purchase-id") or "").strip(),
        "access_token": str(headers.get("x-projectready-access-token") or "").strip(),
    }


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
