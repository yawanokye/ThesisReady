"""Persistent purchases and chapter entitlement usage for ProjectReady AI.

PostgreSQL is used when DATABASE_URL is configured. SQLite is a local-only
fallback so the payment flow can be tested without a Render database.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from typing import Any, Dict, Iterator, Optional

from app.payments.entitlements import action_columns, expiry_datetime, get_plan, normalise_chapter_key, normalise_email, quota_payload

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PAYMENT_DB = os.environ.get(
    "PROJECTREADY_SQLITE_PAYMENT_DB",
    os.environ.get("PROJECTREADY_SQLITE_DB_PATH", "projectready.db"),
)


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS projectready_purchases (
    id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_key TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    chapter_title TEXT,
    academic_level TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency TEXT NOT NULL,
    display_amount NUMERIC(12, 2),
    display_currency TEXT DEFAULT 'USD',
    payment_provider TEXT NOT NULL,
    provider_reference TEXT UNIQUE NOT NULL,
    checkout_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    access_token_hash TEXT NOT NULL,
    drafts_total INTEGER NOT NULL DEFAULT 1,
    drafts_used INTEGER NOT NULL DEFAULT 0,
    revisions_total INTEGER NOT NULL DEFAULT 1,
    revisions_used INTEGER NOT NULL DEFAULT 0,
    compliance_total INTEGER NOT NULL DEFAULT 1,
    compliance_used INTEGER NOT NULL DEFAULT 0,
    exports_total INTEGER NOT NULL DEFAULT 1,
    exports_used INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projectready_payment_events (
    event_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    event_type TEXT,
    payload_hash TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projectready_entitlement_usage (
    id TEXT PRIMARY KEY,
    purchase_id TEXT NOT NULL REFERENCES projectready_purchases(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'claimed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ,
    metadata_json JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_pr_purchase_email ON projectready_purchases(user_email);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_project_chapter ON projectready_purchases(project_id, chapter_key);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_reference ON projectready_purchases(provider_reference);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_status ON projectready_purchases(status);
CREATE INDEX IF NOT EXISTS idx_pr_usage_purchase ON projectready_entitlement_usage(purchase_id);
"""

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projectready_purchases (
    id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_key TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    chapter_title TEXT,
    academic_level TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    display_amount REAL,
    display_currency TEXT DEFAULT 'USD',
    payment_provider TEXT NOT NULL,
    provider_reference TEXT UNIQUE NOT NULL,
    checkout_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    access_token_hash TEXT NOT NULL,
    drafts_total INTEGER NOT NULL DEFAULT 1,
    drafts_used INTEGER NOT NULL DEFAULT 0,
    revisions_total INTEGER NOT NULL DEFAULT 1,
    revisions_used INTEGER NOT NULL DEFAULT 0,
    compliance_total INTEGER NOT NULL DEFAULT 1,
    compliance_used INTEGER NOT NULL DEFAULT 0,
    exports_total INTEGER NOT NULL DEFAULT 1,
    exports_used INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    paid_at TEXT,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projectready_payment_events (
    event_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    event_type TEXT,
    payload_hash TEXT,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projectready_entitlement_usage (
    id TEXT PRIMARY KEY,
    purchase_id TEXT NOT NULL,
    action TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'claimed',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    rolled_back_at TEXT,
    metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY(purchase_id) REFERENCES projectready_purchases(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pr_purchase_email ON projectready_purchases(user_email);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_project_chapter ON projectready_purchases(project_id, chapter_key);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_reference ON projectready_purchases(provider_reference);
CREATE INDEX IF NOT EXISTS idx_pr_purchase_status ON projectready_purchases(status);
CREATE INDEX IF NOT EXISTS idx_pr_usage_purchase ON projectready_entitlement_usage(purchase_id);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _is_postgres(database_url: Optional[str] = None) -> bool:
    value = str(database_url or DATABASE_URL or "").strip().lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


@contextmanager
def _postgres_connection(database_url: str = "") -> Iterator[Any]:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(database_url or DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _sqlite_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(SQLITE_PAYMENT_DB, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_payment_tables(database_url: str = "") -> None:
    """Create payment tables. Safe to call repeatedly."""
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(POSTGRES_SCHEMA)
            conn.commit()
        return

    with _sqlite_connection() as conn:
        conn.executescript(SQLITE_SCHEMA)


def _row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    result = dict(row)
    metadata = result.get("metadata_json")
    if isinstance(metadata, str):
        try:
            result["metadata_json"] = json.loads(metadata)
        except Exception:
            result["metadata_json"] = {}
    return result


def make_provider_reference(provider: str) -> str:
    prefix = "PRAI-PS" if str(provider).lower() == "paystack" else "PRAI-ST"
    random_part = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    return f"{prefix}-{random_part[:24]}"


def create_pending_purchase(
    *,
    user_email: str,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    academic_level: str,
    plan_key: str,
    amount: float,
    currency: str,
    display_amount: float,
    display_currency: str,
    payment_provider: str,
    provider_reference: str,
    metadata: Optional[Dict[str, Any]] = None,
    database_url: str = "",
) -> Dict[str, Any]:
    init_payment_tables(database_url)
    email = normalise_email(user_email)
    if not email or "@" not in email:
        raise ValueError("A valid customer email is required.")
    if not str(project_id or "").strip():
        raise ValueError("project_id is required.")

    plan = get_plan(plan_key)
    quotas = quota_payload(plan_key)
    purchase_id = str(uuid.uuid4())
    access_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(access_token)
    chapter_key = normalise_chapter_key(chapter_number, chapter_title)
    expires_at = expiry_datetime(plan["validity_days"])
    now = _utc_now()

    values = {
        "id": purchase_id,
        "user_email": email,
        "project_id": str(project_id).strip(),
        "chapter_key": chapter_key,
        "chapter_number": int(chapter_number),
        "chapter_title": str(chapter_title or "").strip(),
        "academic_level": str(academic_level or "").strip(),
        "plan_key": str(plan_key).strip().lower(),
        "amount": round(float(amount), 2),
        "currency": str(currency or "").upper(),
        "display_amount": round(float(display_amount), 2),
        "display_currency": str(display_currency or "USD").upper(),
        "payment_provider": str(payment_provider or "").lower(),
        "provider_reference": provider_reference,
        "access_token_hash": token_hash,
        "metadata_json": metadata or {},
        **quotas,
    }

    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO projectready_purchases (
                        id, user_email, project_id, chapter_key, chapter_number, chapter_title,
                        academic_level, plan_key, amount, currency, display_amount, display_currency,
                        payment_provider, provider_reference, access_token_hash,
                        drafts_total, revisions_total, compliance_total, exports_total,
                        metadata_json, expires_at
                    ) VALUES (
                        %(id)s, %(user_email)s, %(project_id)s, %(chapter_key)s, %(chapter_number)s,
                        %(chapter_title)s, %(academic_level)s, %(plan_key)s, %(amount)s, %(currency)s,
                        %(display_amount)s, %(display_currency)s, %(payment_provider)s,
                        %(provider_reference)s, %(access_token_hash)s, %(drafts_total)s,
                        %(revisions_total)s, %(compliance_total)s, %(exports_total)s,
                        %(metadata_json)s::jsonb, %(expires_at)s
                    )
                    RETURNING *
                    """,
                    {**values, "metadata_json": _json(values["metadata_json"]), "expires_at": expires_at},
                )
                row = cur.fetchone()
            conn.commit()
    else:
        with _sqlite_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO projectready_purchases (
                    id, user_email, project_id, chapter_key, chapter_number, chapter_title,
                    academic_level, plan_key, amount, currency, display_amount, display_currency,
                    payment_provider, provider_reference, access_token_hash,
                    drafts_total, revisions_total, compliance_total, exports_total,
                    metadata_json, created_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"], values["user_email"], values["project_id"], values["chapter_key"],
                    values["chapter_number"], values["chapter_title"], values["academic_level"],
                    values["plan_key"], values["amount"], values["currency"], values["display_amount"],
                    values["display_currency"], values["payment_provider"], values["provider_reference"],
                    values["access_token_hash"], values["drafts_total"], values["revisions_total"],
                    values["compliance_total"], values["exports_total"], _json(values["metadata_json"]),
                    now.isoformat(), expires_at.isoformat(), now.isoformat(),
                ),
            )
            row = conn.execute("SELECT * FROM projectready_purchases WHERE id = ?", (purchase_id,)).fetchone()
            conn.commit()

    purchase = _row_to_dict(row) or {}
    purchase["access_token"] = access_token
    return purchase


def set_checkout_session(purchase_id: str, checkout_session_id: str, *, database_url: str = "") -> None:
    if not checkout_session_id:
        return
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE projectready_purchases SET checkout_session_id=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (checkout_session_id, purchase_id),
                )
            conn.commit()
    else:
        with _sqlite_connection() as conn:
            conn.execute(
                "UPDATE projectready_purchases SET checkout_session_id=?, updated_at=? WHERE id=?",
                (checkout_session_id, _utc_iso(), purchase_id),
            )


def get_purchase_by_reference(provider_reference: str, *, database_url: str = "") -> Optional[Dict[str, Any]]:
    init_payment_tables(database_url)
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projectready_purchases WHERE provider_reference=%s", (provider_reference,))
                return _row_to_dict(cur.fetchone())
    with _sqlite_connection() as conn:
        return _row_to_dict(conn.execute("SELECT * FROM projectready_purchases WHERE provider_reference=?", (provider_reference,)).fetchone())


def get_purchase(purchase_id: str, *, database_url: str = "") -> Optional[Dict[str, Any]]:
    init_payment_tables(database_url)
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projectready_purchases WHERE id=%s", (purchase_id,))
                return _row_to_dict(cur.fetchone())
    with _sqlite_connection() as conn:
        return _row_to_dict(conn.execute("SELECT * FROM projectready_purchases WHERE id=?", (purchase_id,)).fetchone())


def get_purchase_by_session(checkout_session_id: str, *, database_url: str = "") -> Optional[Dict[str, Any]]:
    init_payment_tables(database_url)
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projectready_purchases WHERE checkout_session_id=%s", (checkout_session_id,))
                return _row_to_dict(cur.fetchone())
    with _sqlite_connection() as conn:
        return _row_to_dict(conn.execute("SELECT * FROM projectready_purchases WHERE checkout_session_id=?", (checkout_session_id,)).fetchone())


def verify_access_token(purchase_id: str, access_token: str, *, database_url: str = "") -> bool:
    purchase = get_purchase(purchase_id, database_url=database_url)
    if not purchase or not access_token:
        return False
    expected = str(purchase.get("access_token_hash") or "")
    return secrets.compare_digest(expected, _hash_token(access_token))


def activate_purchase(
    *,
    provider_reference: str,
    verified_amount: float,
    verified_currency: str,
    provider_payload: Optional[Dict[str, Any]] = None,
    database_url: str = "",
) -> Dict[str, Any]:
    """Activate a purchase only when verified amount and currency match.

    The update is idempotent, so callback and webhook delivery can safely race.
    """
    purchase = get_purchase_by_reference(provider_reference, database_url=database_url)
    if not purchase:
        raise ValueError("No pending purchase matches the payment reference.")

    expected_amount = round(float(purchase["amount"]), 2)
    actual_amount = round(float(verified_amount), 2)
    expected_currency = str(purchase["currency"]).upper()
    actual_currency = str(verified_currency or "").upper()
    if expected_amount != actual_amount or expected_currency != actual_currency:
        raise ValueError(
            f"Verified payment mismatch. Expected {expected_currency} {expected_amount:.2f}, "
            f"received {actual_currency} {actual_amount:.2f}."
        )

    if str(purchase.get("status")).lower() in {"paid", "active"}:
        return purchase

    metadata = dict(purchase.get("metadata_json") or {})
    metadata["provider_verification"] = provider_payload or {}
    now = _utc_now()

    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE projectready_purchases
                    SET status='paid', paid_at=COALESCE(paid_at, CURRENT_TIMESTAMP),
                        metadata_json=%s::jsonb, updated_at=CURRENT_TIMESTAMP
                    WHERE provider_reference=%s
                    RETURNING *
                    """,
                    (_json(metadata), provider_reference),
                )
                row = cur.fetchone()
            conn.commit()
    else:
        with _sqlite_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE projectready_purchases
                SET status='paid', paid_at=COALESCE(paid_at, ?), metadata_json=?, updated_at=?
                WHERE provider_reference=?
                """,
                (now.isoformat(), _json(metadata), now.isoformat(), provider_reference),
            )
            row = conn.execute("SELECT * FROM projectready_purchases WHERE provider_reference=?", (provider_reference,)).fetchone()
            conn.commit()
    return _row_to_dict(row) or purchase


def record_event_once(
    *, provider: str,
    event_id: str,
    event_type: str,
    raw_body: bytes,
    database_url: str = "",
) -> bool:
    """Return True only for the first delivery of an event."""
    init_payment_tables(database_url)
    event_key = f"{str(provider).lower()}:{event_id}"
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO projectready_payment_events(event_key, provider, event_type, payload_hash)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(event_key) DO NOTHING
                    RETURNING event_key
                    """,
                    (event_key, provider, event_type, payload_hash),
                )
                inserted = cur.fetchone() is not None
            conn.commit()
            return inserted

    with _sqlite_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO projectready_payment_events(event_key, provider, event_type, payload_hash, processed_at) VALUES (?, ?, ?, ?, ?)",
                (event_key, provider, event_type, payload_hash, _utc_iso()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def entitlement_status(purchase_id: str, access_token: str, *, database_url: str = "") -> Dict[str, Any]:
    if not verify_access_token(purchase_id, access_token, database_url=database_url):
        return {"ok": False, "allowed": False, "reason": "invalid_entitlement_token"}
    purchase = get_purchase(purchase_id, database_url=database_url) or {}
    now = _utc_now()
    expires = purchase.get("expires_at")
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except Exception:
            expires = None
    active = str(purchase.get("status", "")).lower() in {"paid", "active"}
    if expires and getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= now:
        active = False

    remaining = {
        "draft": max(int(purchase.get("drafts_total", 0)) - int(purchase.get("drafts_used", 0)), 0),
        "revision": max(int(purchase.get("revisions_total", 0)) - int(purchase.get("revisions_used", 0)), 0),
        "compliance": max(int(purchase.get("compliance_total", 0)) - int(purchase.get("compliance_used", 0)), 0),
        "export": max(int(purchase.get("exports_total", 0)) - int(purchase.get("exports_used", 0)), 0),
    }
    return {
        "ok": True,
        "allowed": active,
        "status": purchase.get("status"),
        "purchase_id": purchase.get("id"),
        "project_id": purchase.get("project_id"),
        "chapter_key": purchase.get("chapter_key"),
        "plan_key": purchase.get("plan_key"),
        "expires_at": str(purchase.get("expires_at")),
        "remaining": remaining,
    }


def claim_entitlement(
    *,
    purchase_id: str,
    access_token: str,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    action: str,
    idempotency_key: str,
    metadata: Optional[Dict[str, Any]] = None,
    database_url: str = "",
) -> Dict[str, Any]:
    """Atomically reserve one chapter action before expensive processing starts."""
    if not idempotency_key:
        raise ValueError("idempotency_key is required.")
    total_col, used_col = action_columns(action)
    expected_chapter = normalise_chapter_key(chapter_number, chapter_title)
    token_hash = _hash_token(access_token)
    usage_id = str(uuid.uuid4())

    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM projectready_entitlement_usage WHERE idempotency_key=%s",
                        (idempotency_key,),
                    )
                    existing = _row_to_dict(cur.fetchone())
                    if existing and existing.get("status") != "rolled_back":
                        raise PermissionError("This chapter action request has already been processed.")

                    cur.execute("SELECT * FROM projectready_purchases WHERE id=%s FOR UPDATE", (purchase_id,))
                    purchase = _row_to_dict(cur.fetchone())
                    _validate_claim_purchase(purchase, token_hash, project_id, expected_chapter, total_col, used_col)
                    cur.execute(
                        f"UPDATE projectready_purchases SET {used_col}={used_col}+1, updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",
                        (purchase_id,),
                    )
                    updated_purchase = _row_to_dict(cur.fetchone())
                    if existing and existing.get("status") == "rolled_back":
                        usage_id = existing["id"]
                        cur.execute(
                            """
                            UPDATE projectready_entitlement_usage
                            SET status='claimed', created_at=CURRENT_TIMESTAMP, completed_at=NULL,
                                rolled_back_at=NULL, metadata_json=%s::jsonb
                            WHERE id=%s
                            RETURNING *
                            """,
                            (_json(metadata), usage_id),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO projectready_entitlement_usage(id, purchase_id, action, idempotency_key, metadata_json)
                            VALUES (%s, %s, %s, %s, %s::jsonb)
                            RETURNING *
                            """,
                            (usage_id, purchase_id, action, idempotency_key, _json(metadata)),
                        )
                    usage = _row_to_dict(cur.fetchone())
                conn.commit()
                return {"ok": True, "claimed": True, "usage": usage, "purchase": updated_purchase}
            except Exception:
                conn.rollback()
                raise

    with _sqlite_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _row_to_dict(conn.execute(
                "SELECT * FROM projectready_entitlement_usage WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone())
            if existing and existing.get("status") != "rolled_back":
                raise PermissionError("This chapter action request has already been processed.")

            purchase = _row_to_dict(conn.execute("SELECT * FROM projectready_purchases WHERE id=?", (purchase_id,)).fetchone())
            _validate_claim_purchase(purchase, token_hash, project_id, expected_chapter, total_col, used_col)
            now = _utc_iso()
            conn.execute(
                f"UPDATE projectready_purchases SET {used_col}={used_col}+1, updated_at=? WHERE id=?",
                (now, purchase_id),
            )
            if existing and existing.get("status") == "rolled_back":
                usage_id = existing["id"]
                conn.execute(
                    """
                    UPDATE projectready_entitlement_usage
                    SET status='claimed', created_at=?, completed_at=NULL, rolled_back_at=NULL, metadata_json=?
                    WHERE id=?
                    """,
                    (now, _json(metadata), usage_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO projectready_entitlement_usage(id, purchase_id, action, idempotency_key, status, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, 'claimed', ?, ?)
                    """,
                    (usage_id, purchase_id, action, idempotency_key, now, _json(metadata)),
                )
            updated = _row_to_dict(conn.execute("SELECT * FROM projectready_purchases WHERE id=?", (purchase_id,)).fetchone())
            usage = _row_to_dict(conn.execute("SELECT * FROM projectready_entitlement_usage WHERE id=?", (usage_id,)).fetchone())
            conn.commit()
            return {"ok": True, "claimed": True, "usage": usage, "purchase": updated}
        except Exception:
            conn.rollback()
            raise


def _validate_claim_purchase(
    purchase: Optional[Dict[str, Any]],
    token_hash: str,
    project_id: str,
    chapter_key: str,
    total_col: str,
    used_col: str,
) -> None:
    if not purchase:
        raise PermissionError("Paid chapter access was not found.")
    if not secrets.compare_digest(str(purchase.get("access_token_hash") or ""), token_hash):
        raise PermissionError("The chapter access token is invalid.")
    if str(purchase.get("status") or "").lower() not in {"paid", "active"}:
        raise PermissionError("Payment has not been confirmed for this chapter.")
    if str(purchase.get("project_id")) != str(project_id):
        raise PermissionError("This purchase belongs to a different project.")
    if str(purchase.get("chapter_key")) != chapter_key:
        raise PermissionError("This purchase belongs to a different chapter.")

    expires = purchase.get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if expires and getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= _utc_now():
        raise PermissionError("This chapter purchase has expired.")
    if int(purchase.get(used_col, 0)) >= int(purchase.get(total_col, 0)):
        raise PermissionError("The included use for this chapter action has already been used.")


def complete_claim(usage_id: str, *, database_url: str = "") -> None:
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE projectready_entitlement_usage SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=%s AND status='claimed'",
                    (usage_id,),
                )
            conn.commit()
    else:
        with _sqlite_connection() as conn:
            conn.execute(
                "UPDATE projectready_entitlement_usage SET status='completed', completed_at=? WHERE id=? AND status='claimed'",
                (_utc_iso(), usage_id),
            )


def rollback_claim(usage_id: str, *, database_url: str = "") -> None:
    """Return a reserved action when generation/check/export fails."""
    if _is_postgres(database_url):
        with _postgres_connection(database_url) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM projectready_entitlement_usage WHERE id=%s FOR UPDATE", (usage_id,))
                    usage = _row_to_dict(cur.fetchone())
                    if not usage or usage.get("status") != "claimed":
                        conn.commit()
                        return
                    _, used_col = action_columns(usage["action"])
                    cur.execute(
                        f"UPDATE projectready_purchases SET {used_col}=GREATEST({used_col}-1, 0), updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (usage["purchase_id"],),
                    )
                    cur.execute(
                        "UPDATE projectready_entitlement_usage SET status='rolled_back', rolled_back_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (usage_id,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return

    with _sqlite_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            usage = _row_to_dict(conn.execute("SELECT * FROM projectready_entitlement_usage WHERE id=?", (usage_id,)).fetchone())
            if not usage or usage.get("status") != "claimed":
                conn.commit()
                return
            _, used_col = action_columns(usage["action"])
            conn.execute(
                f"UPDATE projectready_purchases SET {used_col}=MAX({used_col}-1, 0), updated_at=? WHERE id=?",
                (_utc_iso(), usage["purchase_id"]),
            )
            conn.execute(
                "UPDATE projectready_entitlement_usage SET status='rolled_back', rolled_back_at=? WHERE id=?",
                (_utc_iso(), usage_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
