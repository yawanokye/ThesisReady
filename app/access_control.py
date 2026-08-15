"""Global access policy and page-limited complimentary access for ProjectReady AI.

The public application has three operating modes:
* commercial: normal Free Starter + paid entitlement behaviour;
* temporary_open: paid gates are bypassed until a developer-defined expiry;
* payment_required: Free Starter is disabled and paid/internal/complimentary access is required.

Complimentary access is represented by a random bearer token whose raw value is
shown only once when created. Only a SHA-256 hash is stored. Draft and revision
operations reserve the maximum planned page target so the token cannot be used
beyond its assigned page-credit ceiling. Compliance and export actions are allowed
for an active token without consuming further page credits.
"""
from __future__ import annotations

import hashlib
import math
import re
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional

from app.database import get_conn

POLICY_SCOPE = "all"
VALID_MODES = {"commercial", "temporary_open", "payment_required"}
VALID_PRODUCT_AREAS = {"all", "thesis_workspace", "chapter_strengthener", "topic_ideas"}
PAGE_ACTIONS = {"draft", "revision"}
ZERO_PAGE_ACTIONS = {"compliance", "export"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _normalise_product_area(value: str) -> str:
    area = str(value or "all").strip().lower().replace("-", "_")
    aliases = {
        "workspace": "thesis_workspace",
        "thesis": "thesis_workspace",
        "strengthener": "chapter_strengthener",
        "revision": "chapter_strengthener",
        "topic": "topic_ideas",
        "ideas": "topic_ideas",
    }
    area = aliases.get(area, area)
    if area not in VALID_PRODUCT_AREAS:
        raise ValueError("Unknown ProjectReady product area.")
    return area


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").strip().upper().encode("utf-8")).hexdigest()


def _masked_token_id(token_id: str) -> str:
    value = str(token_id or "")
    return f"COMP-{value[:8].upper()}" if value else "COMP"


def init_access_control_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projectready_access_policy (
                scope TEXT PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'commercial',
                open_until TEXT,
                updated_by TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projectready_complimentary_tokens (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                assigned_email TEXT NOT NULL DEFAULT '',
                product_area TEXT NOT NULL DEFAULT 'all',
                page_limit INTEGER NOT NULL,
                pages_used INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                expires_at TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projectready_complimentary_usage (
                id TEXT PRIMARY KEY,
                token_id TEXT NOT NULL,
                product_area TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                chapter_number INTEGER NOT NULL DEFAULT 0,
                action TEXT NOT NULL,
                reserved_pages INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'reserved',
                idempotency_key TEXT NOT NULL UNIQUE,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                rolled_back_at TEXT,
                FOREIGN KEY(token_id) REFERENCES projectready_complimentary_tokens(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_comp_token_hash ON projectready_complimentary_tokens(token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_comp_usage_token ON projectready_complimentary_usage(token_id, created_at)")
        row = conn.execute("SELECT scope FROM projectready_access_policy WHERE scope=?", (POLICY_SCOPE,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO projectready_access_policy(scope, mode, open_until, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)",
                (POLICY_SCOPE, "commercial", None, "system", _iso()),
            )
        conn.commit()


def get_access_policy() -> Dict[str, Any]:
    init_access_control_tables()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projectready_access_policy WHERE scope=?", (POLICY_SCOPE,)).fetchone()
    data = dict(row) if row else {"scope": POLICY_SCOPE, "mode": "commercial", "open_until": None}
    mode = str(data.get("mode") or "commercial")
    if mode not in VALID_MODES:
        mode = "commercial"
    open_until = _parse_time(data.get("open_until"))
    if mode == "temporary_open" and (not open_until or open_until <= _utc_now()):
        set_access_policy("commercial", updated_by="automatic_expiry")
        mode = "commercial"
        open_until = None
    return {
        "scope": POLICY_SCOPE,
        "mode": mode,
        "open_until": _iso(open_until) if open_until else None,
        "updated_by": str(data.get("updated_by") or ""),
        "updated_at": str(data.get("updated_at") or ""),
        "temporary_open": mode == "temporary_open",
        "free_starter_enabled": mode != "payment_required",
        "payment_required": mode == "payment_required",
    }


def set_access_policy(
    mode: str,
    *,
    open_hours: Optional[float] = None,
    open_until: Optional[datetime] = None,
    updated_by: str = "developer",
) -> Dict[str, Any]:
    init_access_control_tables()
    normalised = str(mode or "commercial").strip().lower().replace("-", "_")
    if normalised in {"open", "temporary", "temporarily_open"}:
        normalised = "temporary_open"
    if normalised in {"paid", "locked", "force_payment", "payment"}:
        normalised = "payment_required"
    if normalised not in VALID_MODES:
        raise ValueError("Access mode must be commercial, temporary_open, or payment_required.")

    expiry: Optional[datetime] = None
    if normalised == "temporary_open":
        if open_until:
            expiry = open_until.astimezone(timezone.utc)
        else:
            try:
                hours = float(open_hours if open_hours is not None else 1)
            except Exception:
                hours = 1.0
            hours = max(0.25, min(hours, 168.0))
            expiry = _utc_now() + timedelta(hours=hours)
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projectready_access_policy
            SET mode=?, open_until=?, updated_by=?, updated_at=?
            WHERE scope=?
            """,
            (normalised, _iso(expiry) if expiry else None, str(updated_by or "developer")[:254], _iso(), POLICY_SCOPE),
        )
        conn.commit()
    return get_access_policy()


def public_access_status(product_area: str = "all") -> Dict[str, Any]:
    area = _normalise_product_area(product_area)
    policy = get_access_policy()
    mode = policy["mode"]
    if mode == "temporary_open":
        message = "Temporary open access is active. No chapter payment is required while this access window remains open."
    elif mode == "payment_required":
        message = "Payment access is currently required for generation and strengthening. Complimentary and authorised internal access remain valid."
    else:
        message = "Normal commercial access is active, including the configured Free Starter where applicable."
    return {
        "ok": True,
        "product_area": area,
        "mode": mode,
        "open_until": policy.get("open_until"),
        "free_starter_enabled": bool(policy.get("free_starter_enabled")),
        "payment_required": bool(policy.get("payment_required")),
        "temporary_open": bool(policy.get("temporary_open")),
        "message": message,
    }


def issue_complimentary_token(
    *,
    page_limit: int,
    label: str = "",
    assigned_email: str = "",
    product_area: str = "all",
    validity_days: int = 30,
    created_by: str = "developer",
) -> Dict[str, Any]:
    init_access_control_tables()
    area = _normalise_product_area(product_area)
    pages = max(1, min(int(page_limit or 0), 1000))
    days = max(1, min(int(validity_days or 30), 365))
    email = str(assigned_email or "").strip().lower()
    if email and ("@" not in email or len(email) > 254):
        raise ValueError("Assigned email must be a valid email address or left blank.")
    token_id = str(uuid.uuid4())
    raw_token = "PRAI-COMP-" + secrets.token_urlsafe(20).replace("-", "").replace("_", "")[:28].upper()
    now = _utc_now()
    expires = now + timedelta(days=days)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projectready_complimentary_tokens
                (id, token_hash, label, assigned_email, product_area, page_limit, pages_used, status, expires_at, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, ?)
            """,
            (
                token_id,
                _hash_token(raw_token),
                str(label or "Complimentary access")[:200],
                email,
                area,
                pages,
                _iso(expires),
                str(created_by or "developer")[:254],
                _iso(now),
                _iso(now),
            ),
        )
        conn.commit()
    return {
        "ok": True,
        "id": token_id,
        "token": raw_token,
        "masked_id": _masked_token_id(token_id),
        "label": str(label or "Complimentary access")[:200],
        "assigned_email": email,
        "product_area": area,
        "page_limit": pages,
        "pages_used": 0,
        "pages_remaining": pages,
        "expires_at": _iso(expires),
        "message": "Complimentary token created. Copy it now because the raw token is not stored and cannot be shown again.",
    }


def _token_row(raw_token: str) -> Optional[Dict[str, Any]]:
    init_access_control_tables()
    token_hash = _hash_token(raw_token)
    if not raw_token or not re.fullmatch(r"PRAI-COMP-[A-Z0-9]{12,64}", str(raw_token or "").strip().upper()):
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projectready_complimentary_tokens WHERE token_hash=?", (token_hash,)).fetchone()
    return dict(row) if row else None


def validate_complimentary_token(
    raw_token: str,
    *,
    product_area: str = "all",
    supplied_email: str = "",
    require_pages: int = 0,
) -> Dict[str, Any]:
    area = _normalise_product_area(product_area)
    row = _token_row(raw_token)
    if not row:
        raise PermissionError("The complimentary access token is invalid.")
    if str(row.get("status") or "") != "active":
        raise PermissionError("This complimentary access token is no longer active.")
    expires = _parse_time(row.get("expires_at"))
    if not expires or expires <= _utc_now():
        raise PermissionError("This complimentary access token has expired.")
    token_area = _normalise_product_area(str(row.get("product_area") or "all"))
    if token_area != "all" and area != "all" and token_area != area:
        raise PermissionError("This complimentary token is not valid for this ProjectReady module.")
    assigned_email = str(row.get("assigned_email") or "").strip().lower()
    supplied = str(supplied_email or "").strip().lower()
    if assigned_email and supplied != assigned_email:
        raise PermissionError("Enter the email address assigned to this complimentary token.")
    page_limit = int(row.get("page_limit") or 0)
    pages_used = int(row.get("pages_used") or 0)
    remaining = max(0, page_limit - pages_used)
    needed = max(0, int(math.ceil(float(require_pages or 0))))
    if needed > remaining:
        raise PermissionError(
            f"This complimentary token has {remaining} page credit(s) remaining, but the selected generation target requires {needed}. Reduce the custom page target or use paid access."
        )
    return {
        "ok": True,
        "allowed": True,
        "id": row.get("id"),
        "masked_id": _masked_token_id(str(row.get("id") or "")),
        "label": row.get("label") or "Complimentary access",
        "assigned_email": assigned_email,
        "product_area": token_area,
        "page_limit": page_limit,
        "pages_used": pages_used,
        "pages_remaining": remaining,
        "expires_at": _iso(expires),
    }


def complimentary_status(raw_token: str, *, product_area: str = "all", supplied_email: str = "") -> Dict[str, Any]:
    return validate_complimentary_token(
        raw_token,
        product_area=product_area,
        supplied_email=supplied_email,
        require_pages=0,
    )


def list_complimentary_tokens(limit: int = 100) -> list[Dict[str, Any]]:
    init_access_control_tables()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, label, assigned_email, product_area, page_limit, pages_used, status,
                   expires_at, created_by, created_at, updated_at
            FROM projectready_complimentary_tokens
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 100), 500)),),
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["masked_id"] = _masked_token_id(str(item.get("id") or ""))
        item["pages_remaining"] = max(0, int(item.get("page_limit") or 0) - int(item.get("pages_used") or 0))
        expiry = _parse_time(item.get("expires_at"))
        item["expired"] = not expiry or expiry <= _utc_now()
        if item["expired"] and item.get("status") == "active":
            item["effective_status"] = "expired"
        else:
            item["effective_status"] = item.get("status") or "unknown"
        output.append(item)
    return output


def revoke_complimentary_token(token_id: str, *, updated_by: str = "developer") -> Dict[str, Any]:
    init_access_control_tables()
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE projectready_complimentary_tokens SET status='revoked', updated_at=? WHERE id=?",
            (_iso(), str(token_id or "")),
        )
        conn.commit()
        if not getattr(cur, "rowcount", 0):
            raise ValueError("Complimentary token was not found.")
    return {"ok": True, "id": token_id, "status": "revoked", "updated_by": updated_by}


def complimentary_token_from_request(request: Any) -> tuple[str, str]:
    headers = getattr(request, "headers", {})
    token = str(headers.get("x-projectready-complimentary-token") or "").strip().upper()
    email = str(headers.get("x-projectready-complimentary-email") or "").strip().lower()
    return token, email


def complete_complimentary_usage(usage_id: str) -> None:
    if not usage_id:
        return
    init_access_control_tables()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projectready_complimentary_usage SET status='completed', completed_at=? WHERE id=? AND status='reserved'",
            (_iso(), str(usage_id)),
        )
        conn.commit()


def rollback_complimentary_usage(usage_id: str) -> None:
    if not usage_id:
        return
    init_access_control_tables()
    with get_conn() as conn:
        usage = conn.execute("SELECT * FROM projectready_complimentary_usage WHERE id=?", (str(usage_id),)).fetchone()
        if not usage:
            return
        data = dict(usage)
        if str(data.get("status") or "") != "reserved":
            return
        reserved = max(0, int(data.get("reserved_pages") or 0))
        token_id = str(data.get("token_id") or "")
        if reserved:
            conn.execute(
                "UPDATE projectready_complimentary_tokens SET pages_used=CASE WHEN pages_used>=? THEN pages_used-? ELSE 0 END, updated_at=? WHERE id=?",
                (reserved, reserved, _iso(), token_id),
            )
        conn.execute(
            "UPDATE projectready_complimentary_usage SET status='rolled_back', rolled_back_at=? WHERE id=? AND status='reserved'",
            (_iso(), str(usage_id)),
        )
        conn.commit()


@contextmanager
def complimentary_action(
    *,
    raw_token: str,
    supplied_email: str,
    product_area: str,
    project_id: str,
    chapter_number: int,
    action: str,
    requested_pages: int = 0,
    idempotency_key: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict[str, Any]]:
    action_key = str(action or "").strip().lower()
    if action_key not in PAGE_ACTIONS | ZERO_PAGE_ACTIONS:
        raise PermissionError("This complimentary token cannot be used for the requested action.")
    reserved_pages = max(0, int(math.ceil(float(requested_pages or 0)))) if action_key in PAGE_ACTIONS else 0
    status = validate_complimentary_token(
        raw_token,
        product_area=product_area,
        supplied_email=supplied_email,
        require_pages=reserved_pages,
    )
    token_id = str(status.get("id") or "")
    usage_id = str(uuid.uuid4())
    key = str(idempotency_key or uuid.uuid4())

    init_access_control_tables()
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM projectready_complimentary_usage WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            existing_data = dict(existing)
            if existing_data.get("token_id") != token_id:
                raise PermissionError("This request key belongs to a different complimentary token.")
            if str(existing_data.get("status") or "") == "completed":
                yield {
                    "claimed": False,
                    "complimentary_access": True,
                    "complimentary_usage_id": existing_data.get("id"),
                    "reserved_pages": int(existing_data.get("reserved_pages") or 0),
                    "token": status,
                }
                return
            if str(existing_data.get("status") or "") == "reserved":
                usage_id = str(existing_data.get("id") or usage_id)
                reserved_pages = int(existing_data.get("reserved_pages") or reserved_pages)
            else:
                existing = None

        if not existing:
            if reserved_pages:
                cur = conn.execute(
                    """
                    UPDATE projectready_complimentary_tokens
                    SET pages_used=pages_used+?, updated_at=?
                    WHERE id=? AND status='active' AND (pages_used+?)<=page_limit
                    """,
                    (reserved_pages, _iso(), token_id, reserved_pages),
                )
                if not getattr(cur, "rowcount", 0):
                    conn.rollback()
                    refreshed = validate_complimentary_token(
                        raw_token,
                        product_area=product_area,
                        supplied_email=supplied_email,
                        require_pages=0,
                    )
                    raise PermissionError(
                        f"This complimentary token has {refreshed['pages_remaining']} page credit(s) remaining. Reduce the selected page target or use paid access."
                    )
            import json
            conn.execute(
                """
                INSERT INTO projectready_complimentary_usage
                    (id, token_id, product_area, project_id, chapter_number, action, reserved_pages, status, idempotency_key, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, ?)
                """,
                (
                    usage_id,
                    token_id,
                    _normalise_product_area(product_area),
                    str(project_id or ""),
                    int(chapter_number or 0),
                    action_key,
                    reserved_pages,
                    key,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                    _iso(),
                ),
            )
            conn.commit()

    claim = {
        "claimed": True,
        "complimentary_access": True,
        "access_type": "complimentary_pages",
        "complimentary_usage_id": usage_id,
        "reserved_pages": reserved_pages,
        "token": status,
    }
    try:
        yield claim
    except Exception:
        rollback_complimentary_usage(usage_id)
        raise
    else:
        complete_complimentary_usage(usage_id)


def reserve_complimentary_for_background(
    *,
    raw_token: str,
    supplied_email: str,
    product_area: str,
    project_id: str,
    chapter_number: int,
    action: str,
    requested_pages: int,
    idempotency_key: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reserve complimentary page credits for a background job without completing them."""
    action_key = str(action or "").strip().lower()
    reserved_pages = max(0, int(math.ceil(float(requested_pages or 0)))) if action_key in PAGE_ACTIONS else 0
    status = validate_complimentary_token(
        raw_token,
        product_area=product_area,
        supplied_email=supplied_email,
        require_pages=reserved_pages,
    )
    token_id = str(status.get("id") or "")
    usage_id = str(uuid.uuid4())
    key = str(idempotency_key or uuid.uuid4())
    init_access_control_tables()
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM projectready_complimentary_usage WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            data = dict(existing)
            if data.get("token_id") != token_id:
                raise PermissionError("This request key belongs to a different complimentary token.")
            return {
                "claimed": str(data.get("status") or "") == "reserved",
                "complimentary_access": True,
                "access_type": "complimentary_pages",
                "complimentary_usage_id": data.get("id"),
                "reserved_pages": int(data.get("reserved_pages") or 0),
                "token_id": token_id,
            }
        if reserved_pages:
            cur = conn.execute(
                "UPDATE projectready_complimentary_tokens SET pages_used=pages_used+?, updated_at=? WHERE id=? AND status='active' AND (pages_used+?)<=page_limit",
                (reserved_pages, _iso(), token_id, reserved_pages),
            )
            if not getattr(cur, "rowcount", 0):
                conn.rollback()
                refreshed = validate_complimentary_token(raw_token, product_area=product_area, supplied_email=supplied_email, require_pages=0)
                raise PermissionError(f"This complimentary token has {refreshed['pages_remaining']} page credit(s) remaining. Reduce the selected page target or use paid access.")
        import json
        conn.execute(
            """
            INSERT INTO projectready_complimentary_usage
                (id, token_id, product_area, project_id, chapter_number, action, reserved_pages, status, idempotency_key, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, ?)
            """,
            (usage_id, token_id, _normalise_product_area(product_area), str(project_id or ""), int(chapter_number or 0), action_key, reserved_pages, key, json.dumps(metadata or {}, ensure_ascii=False, default=str), _iso()),
        )
        conn.commit()
    return {
        "claimed": True,
        "complimentary_access": True,
        "access_type": "complimentary_pages",
        "complimentary_usage_id": usage_id,
        "reserved_pages": reserved_pages,
        "token_id": token_id,
        "product_area": _normalise_product_area(product_area),
    }
