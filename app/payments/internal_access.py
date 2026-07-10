"""Internal developer entitlement helpers for ProjectReady AI.

This module creates a hidden, non-payment access route for trusted developers.
It deliberately requires both an allow-listed email and a six-digit key. The
credential is signed server-side and is accepted by the normal entitlement guard
without creating public trial access or touching Paystack/Stripe.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any, Dict, Iterable, Optional

INTERNAL_PURCHASE_PREFIX = "pr-internal-v1"
DEFAULT_VALIDITY_HOURS = 12
INTERNAL_QUOTA = 999

_PRODUCT_AREAS = {
    "all",
    "thesis_workspace",
    "chapter_strengthener",
    "topic_ideas",
}

_ACTIONS_BY_PRODUCT = {
    "thesis_workspace": {"draft", "revision", "compliance", "export"},
    "chapter_strengthener": {"revision", "compliance", "export"},
    "topic_ideas": {"draft"},
    "all": {"draft", "revision", "compliance", "export"},
}


def _normalise_email(email: str) -> str:
    return str(email or "").strip().lower()


def _split_env_list(value: str) -> list[str]:
    return [item.strip().lower() for item in re.split(r"[,;\s]+", str(value or "")) if item.strip()]


def _allowed_emails() -> set[str]:
    raw = os.getenv("PROJECTREADY_INTERNAL_ACCESS_EMAILS", "")
    return set(_split_env_list(raw))


def internal_access_configured() -> bool:
    return bool(_allowed_emails()) and bool(_configured_key_hash() or _configured_plain_key())


def _configured_plain_key() -> str:
    # The key is intentionally six digits. It is not a public trial key because
    # it only works with allow-listed email addresses and produces signed,
    # time-limited credentials.
    return str(
        os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY")
        or os.getenv("PROJECTREADY_INTERNAL_ACCESS_PIN")
        or ""
    ).strip()


def _configured_key_hash() -> str:
    return str(
        os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256")
        or os.getenv("PROJECTREADY_INTERNAL_ACCESS_PIN_SHA256")
        or ""
    ).strip().lower()


def _signing_secret() -> bytes:
    raw = str(
        os.getenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET")
        or os.getenv("SECRET_KEY")
        or _configured_key_hash()
        or _configured_plain_key()
        or ""
    ).strip()
    if not raw:
        raise PermissionError("Internal access signing is not configured.")
    return hashlib.sha256(("projectready-internal-access:" + raw).encode("utf-8")).digest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    text = str(value or "")
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _normalise_product_area(value: str) -> str:
    area = str(value or "all").strip().lower().replace("-", "_")
    if area in {"workspace", "thesis", "chapter", "drafting"}:
        area = "thesis_workspace"
    if area in {"strengthener", "chapter_revision", "revision_only"}:
        area = "chapter_strengthener"
    if area in {"topic", "ideas", "topic_idea"}:
        area = "topic_ideas"
    if area not in _PRODUCT_AREAS:
        raise ValueError("Unknown internal access product area.")
    return area


def _normalise_chapter_number(value: Any) -> int:
    try:
        number = int(value or 0)
    except Exception:
        number = 0
    return max(0, min(number, 99))


def _verify_email_allowed(email: str) -> str:
    clean = _normalise_email(email)
    if not clean or "@" not in clean:
        raise PermissionError("Enter a valid allow-listed developer email.")
    allowed = _allowed_emails()
    if not allowed:
        raise PermissionError("Internal access email allow-list is not configured.")
    if clean not in allowed:
        raise PermissionError("This email is not authorised for internal access.")
    return clean


def _verify_six_digit_key(supplied: str) -> None:
    key = str(supplied or "").strip()
    if not re.fullmatch(r"\d{6}", key):
        raise PermissionError("Enter the six-digit internal access key.")

    configured_hash = _configured_key_hash()
    configured_plain = _configured_plain_key()
    if not configured_hash and not configured_plain:
        raise PermissionError("Internal access key is not configured.")

    supplied_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if configured_hash:
        if hmac.compare_digest(supplied_hash.encode("utf-8"), configured_hash.encode("utf-8")):
            return
        raise PermissionError("The internal access key is invalid.")

    if not re.fullmatch(r"\d{6}", configured_plain):
        raise PermissionError("PROJECTREADY_INTERNAL_ACCESS_KEY must be exactly six digits.")
    if not hmac.compare_digest(key.encode("utf-8"), configured_plain.encode("utf-8")):
        raise PermissionError("The internal access key is invalid.")


def _build_token(payload: Dict[str, Any]) -> str:
    encoded = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_signing_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"pr_int_v1.{encoded}.{_b64url(signature)}"


def _read_token(token: str) -> Dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3 or parts[0] != "pr_int_v1":
        raise PermissionError("The internal access token is invalid.")
    signing_input = parts[1].encode("ascii")
    expected = hmac.new(_signing_secret(), signing_input, hashlib.sha256).digest()
    supplied = _b64url_decode(parts[2])
    if not hmac.compare_digest(expected, supplied):
        raise PermissionError("The internal access token signature is invalid.")
    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as exc:
        raise PermissionError("The internal access token payload is invalid.") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise PermissionError("Internal access has expired. Re-enter the developer key.")
    return payload


def issue_internal_access(
    *,
    email: str,
    key: str,
    product_area: str = "all",
    project_id: str = "",
    chapter_number: Any = 0,
    chapter_title: str = "",
    validity_hours: Optional[int] = None,
) -> Dict[str, Any]:
    clean_email = _verify_email_allowed(email)
    _verify_six_digit_key(key)
    area = _normalise_product_area(product_area)
    hours = int(validity_hours or os.getenv("PROJECTREADY_INTERNAL_ACCESS_HOURS", DEFAULT_VALIDITY_HOURS) or DEFAULT_VALIDITY_HOURS)
    hours = max(1, min(hours, 168))
    now = int(time.time())
    payload = {
        "typ": "projectready_internal_access",
        "email": clean_email,
        "product_area": area,
        "project_id": str(project_id or ""),
        "chapter_number": _normalise_chapter_number(chapter_number),
        "chapter_title": str(chapter_title or "")[:200],
        "iat": now,
        "exp": now + hours * 3600,
        "nonce": secrets.token_urlsafe(12),
    }
    token = _build_token(payload)
    purchase_id = f"{INTERNAL_PURCHASE_PREFIX}:{area}:{payload['nonce']}"
    return {
        "ok": True,
        "access_type": "internal_admin",
        "provider": "internal_admin",
        "purchase_id": purchase_id,
        "access_token": token,
        "email": clean_email,
        "product_area": area,
        "project_id": payload["project_id"],
        "chapter_number": payload["chapter_number"],
        "chapter_title": payload["chapter_title"],
        "expires_at": payload["exp"],
        "validity_hours": hours,
        "message": "Internal developer access activated for this device.",
    }


def is_internal_purchase_id(purchase_id: str) -> bool:
    return str(purchase_id or "").startswith(INTERNAL_PURCHASE_PREFIX + ":")


def validate_internal_access(
    *,
    purchase_id: str,
    access_token: str,
    product_area: str = "all",
    project_id: str = "",
    chapter_number: Any = 0,
    action: str = "",
) -> Dict[str, Any]:
    if not is_internal_purchase_id(purchase_id):
        raise PermissionError("Not an internal access credential.")
    payload = _read_token(access_token)
    _verify_email_allowed(str(payload.get("email") or ""))
    token_area = _normalise_product_area(str(payload.get("product_area") or "all"))
    requested_area = _normalise_product_area(product_area or token_area)
    if requested_area != "all" and token_area != "all" and token_area != requested_area:
        raise PermissionError("This internal access key is not valid for this module.")
    action_key = str(action or "").strip().lower()
    if action_key and action_key not in _ACTIONS_BY_PRODUCT.get(token_area, set()) and action_key not in _ACTIONS_BY_PRODUCT.get(requested_area, set()):
        raise PermissionError("This internal access key does not include the requested action.")
    token_project = str(payload.get("project_id") or "").strip()
    requested_project = str(project_id or "").strip()
    if token_project and requested_project and token_project != requested_project:
        raise PermissionError("This internal access key was issued for a different project.")
    token_chapter = _normalise_chapter_number(payload.get("chapter_number"))
    requested_chapter = _normalise_chapter_number(chapter_number)
    if token_chapter and requested_chapter and token_chapter != requested_chapter:
        raise PermissionError("This internal access key was issued for a different chapter.")
    return {
        "ok": True,
        "allowed": True,
        "access_type": "internal_admin",
        "provider": "internal_admin",
        "purchase_id": purchase_id,
        "product_area": token_area,
        "requested_product_area": requested_area,
        "project_id": token_project or requested_project,
        "chapter_number": token_chapter or requested_chapter,
        "chapter_key": f"chapter-{token_chapter or requested_chapter}" if (token_chapter or requested_chapter) else "",
        "email": str(payload.get("email") or ""),
        "expires_at_epoch": int(payload.get("exp") or 0),
        "remaining": {
            "draft": INTERNAL_QUOTA,
            "revision": INTERNAL_QUOTA,
            "compliance": INTERNAL_QUOTA,
            "export": INTERNAL_QUOTA,
        },
        "message": "Internal developer access is active. No payment quota will be consumed.",
    }


def internal_entitlement_status(
    *,
    purchase_id: str,
    access_token: str,
    product_area: str = "all",
    project_id: str = "",
    chapter_number: Any = 0,
) -> Dict[str, Any]:
    status = validate_internal_access(
        purchase_id=purchase_id,
        access_token=access_token,
        product_area=product_area,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    status.update({
        "status": "active",
        "allowed": True,
        "plan_key": "internal_admin_access",
        "expires_at": "developer_session",
        "used": {"draft": 0, "revision": 0, "compliance": 0, "export": 0},
        "totals": {
            "draft": INTERNAL_QUOTA,
            "revision": INTERNAL_QUOTA,
            "compliance": INTERNAL_QUOTA,
            "export": INTERNAL_QUOTA,
        },
    })
    return status
