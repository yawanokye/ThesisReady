from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.database import get_conn

ACTIVE_STATUSES = {"queued", "running", "retrying"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat()


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def _row(row: Any | None, *, include_payload: bool = True) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    payload = _loads(data.pop("payload_json", "{}"), {})
    result = _loads(data.pop("result_json", "{}"), {})
    if include_payload:
        data["payload"] = payload
    data["result"] = result
    return data


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def init_job_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projectready_jobs (
                id TEXT PRIMARY KEY,
                job_token_hash TEXT NOT NULL,
                job_type TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                chapter_number INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                stage TEXT NOT NULL DEFAULT 'queued',
                message TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error_text TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 2,
                locked_by TEXT,
                lease_expires_at TEXT,
                available_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_jobs_status_available ON projectready_jobs(status, available_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_jobs_project ON projectready_jobs(project_id, chapter_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_jobs_created ON projectready_jobs(created_at)")
        conn.commit()


def create_job(
    *,
    job_type: str,
    payload: dict[str, Any],
    project_id: str = "",
    chapter_number: int = 0,
    max_attempts: int = 2,
    job_id: str | None = None,
    message: str = "Request queued for background processing.",
) -> tuple[dict[str, Any], str]:
    init_job_tables()
    identifier = str(job_id or uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = _iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projectready_jobs(
                id, job_token_hash, job_type, project_id, chapter_number,
                status, progress, stage, message, payload_json, result_json,
                error_text, attempts, max_attempts, available_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', 0, 'queued', ?, ?, '{}', '', 0, ?, ?, ?, ?)
            """,
            (
                identifier,
                _hash_token(token),
                str(job_type or "").strip(),
                str(project_id or "").strip(),
                int(chapter_number or 0),
                str(message or "")[:500],
                json.dumps(payload or {}, ensure_ascii=False, default=str),
                max(1, min(int(max_attempts or 2), 5)),
                now,
                now,
                now,
            ),
        )
        conn.commit()
    return get_job(identifier, include_payload=True) or {}, token


def get_job(job_id: str, *, include_payload: bool = False) -> dict[str, Any] | None:
    init_job_tables()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projectready_jobs WHERE id = ?", (str(job_id or ""),)).fetchone()
    return _row(row, include_payload=include_payload)


def verify_job_token(job_id: str, token: str) -> bool:
    if not job_id or not token:
        return False
    with get_conn() as conn:
        row = conn.execute("SELECT job_token_hash FROM projectready_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return False
    supplied = _hash_token(token)
    stored = str(dict(row).get("job_token_hash") or "")
    return secrets.compare_digest(supplied, stored)


def find_active_job(*, job_type: str, project_id: str, chapter_number: int) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    params: list[Any] = [job_type, project_id, int(chapter_number or 0), *sorted(ACTIVE_STATUSES)]
    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT * FROM projectready_jobs
            WHERE job_type = ? AND project_id = ? AND chapter_number = ?
              AND status IN ({placeholders})
            ORDER BY created_at DESC LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    return _row(row, include_payload=False)


def requeue_stale_jobs() -> int:
    now = _iso()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE projectready_jobs
            SET status='queued', stage='recovered', progress=CASE WHEN progress < 5 THEN 5 ELSE progress END,
                message='Recovered after a worker interruption and returned to the queue.',
                locked_by=NULL, lease_expires_at=NULL, available_at=?, updated_at=?
            WHERE status='running' AND attempts < max_attempts AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now, now, now),
        )
        count = int(getattr(cursor, "rowcount", 0) or 0)
        conn.commit()
    return count


def fail_exhausted_stale_jobs() -> list[dict[str, Any]]:
    """Fail worker-interrupted jobs that have no attempts left.

    The worker uses the returned payloads to roll back any reserved paid
    entitlement. This prevents a repeatedly crashing request from remaining in
    the queue forever.
    """
    init_job_tables()
    now = _iso()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM projectready_jobs
            WHERE status='running' AND attempts >= max_attempts
              AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now,),
        ).fetchall()
        jobs = [_row(row, include_payload=True) for row in rows]
        if jobs:
            identifiers = [str(job.get("id") or "") for job in jobs if job]
            placeholders = ",".join("?" for _ in identifiers)
            conn.execute(
                f"""
                UPDATE projectready_jobs
                SET status='failed', stage='failed', progress=100,
                    message='Background processing stopped after repeated worker interruptions.',
                    error_text='The worker was interrupted before the request could finish.',
                    locked_by=NULL, lease_expires_at=NULL, completed_at=?, updated_at=?
                WHERE id IN ({placeholders})
                """,
                (now, now, *identifiers),
            )
            conn.commit()
    return [job for job in jobs if job]


def claim_next_job(*, worker_id: str, lease_seconds: int = 2400, job_types: Iterable[str] | None = None) -> dict[str, Any] | None:
    init_job_tables()
    requeue_stale_jobs()
    now = _iso()
    lease = _iso(_utc_now() + timedelta(seconds=max(300, int(lease_seconds or 2400))))
    types = [str(item).strip() for item in (job_types or []) if str(item).strip()]
    where_type = ""
    params: list[Any] = [now]
    if types:
        where_type = " AND job_type IN (" + ",".join("?" for _ in types) + ")"
        params.extend(types)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id FROM projectready_jobs
            WHERE status IN ('queued', 'retrying')
              AND (available_at IS NULL OR available_at <= ?)
              {where_type}
            ORDER BY created_at ASC LIMIT 12
            """,
            tuple(params),
        ).fetchall()
        for candidate in rows:
            candidate_id = str(dict(candidate).get("id") or "")
            cursor = conn.execute(
                """
                UPDATE projectready_jobs
                SET status='running', stage='starting', progress=5,
                    message='A background worker has started this request.',
                    attempts=attempts+1, locked_by=?, lease_expires_at=?, updated_at=?
                WHERE id=? AND status IN ('queued', 'retrying')
                """,
                (worker_id, lease, now, candidate_id),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) == 1:
                conn.commit()
                row = conn.execute("SELECT * FROM projectready_jobs WHERE id=?", (candidate_id,)).fetchone()
                return _row(row, include_payload=True)
        conn.commit()
    return None


def renew_lease(job_id: str, *, worker_id: str, lease_seconds: int = 2400) -> None:
    lease = _iso(_utc_now() + timedelta(seconds=max(300, int(lease_seconds or 2400))))
    now = _iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projectready_jobs SET lease_expires_at=?, updated_at=? WHERE id=? AND status='running' AND locked_by=?",
            (lease, now, job_id, worker_id),
        )
        conn.commit()


def update_job(job_id: str, *, progress: int | None = None, stage: str | None = None, message: str | None = None) -> None:
    fields = ["updated_at=?"]
    values: list[Any] = [_iso()]
    if progress is not None:
        fields.append("progress=?")
        values.append(max(0, min(int(progress), 100)))
    if stage is not None:
        fields.append("stage=?")
        values.append(str(stage or "")[:120])
    if message is not None:
        fields.append("message=?")
        values.append(str(message or "")[:500])
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE projectready_jobs SET {', '.join(fields)} WHERE id=?", tuple(values))
        conn.commit()


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    now = _iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projectready_jobs
            SET status='completed', progress=100, stage='completed',
                message='Background processing completed successfully.', result_json=?,
                error_text='', locked_by=NULL, lease_expires_at=NULL,
                completed_at=?, updated_at=?
            WHERE id=?
            """,
            (json.dumps(result or {}, ensure_ascii=False, default=str), now, now, job_id),
        )
        conn.commit()


def fail_or_retry_job(job_id: str, error: str, *, permanent: bool = False) -> dict[str, Any] | None:
    job = get_job(job_id, include_payload=True)
    if not job:
        return None
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 1)
    now = _iso()
    if not permanent and attempts < max_attempts:
        delay = min(300, 20 * max(1, attempts))
        available = _iso(_utc_now() + timedelta(seconds=delay))
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE projectready_jobs
                SET status='retrying', stage='retrying', progress=10,
                    message=?, error_text=?, available_at=?, locked_by=NULL,
                    lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    f"The request will retry automatically in about {delay} seconds.",
                    str(error or "")[:4000],
                    available,
                    now,
                    job_id,
                ),
            )
            conn.commit()
    else:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE projectready_jobs
                SET status='failed', stage='failed', progress=100,
                    message='Background processing could not be completed.', error_text=?,
                    locked_by=NULL, lease_expires_at=NULL, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (str(error or "")[:4000], now, now, job_id),
            )
            conn.commit()
    return get_job(job_id, include_payload=True)


def cancel_job(job_id: str) -> dict[str, Any] | None:
    now = _iso()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE projectready_jobs
            SET status='cancelled', stage='cancelled', progress=100,
                message='This background request was cancelled.', locked_by=NULL,
                lease_expires_at=NULL, completed_at=?, updated_at=?
            WHERE id=? AND status IN ('queued', 'retrying')
            """,
            (now, now, job_id),
        )
        conn.commit()
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            return get_job(job_id, include_payload=True)
    return get_job(job_id, include_payload=True)


def retry_job(job_id: str) -> dict[str, Any] | None:
    now = _iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projectready_jobs
            SET status='queued', stage='queued', progress=0, attempts=0,
                message='Request returned to the background queue.', error_text='',
                available_at=?, locked_by=NULL, lease_expires_at=NULL,
                completed_at=NULL, updated_at=?
            WHERE id=? AND status IN ('failed', 'cancelled')
            """,
            (now, now, job_id),
        )
        conn.commit()
    return get_job(job_id, include_payload=True)


def list_jobs(*, limit: int = 50, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    states = [str(item).strip() for item in (statuses or []) if str(item).strip()]
    where = ""
    params: list[Any] = []
    if states:
        where = " WHERE status IN (" + ",".join("?" for _ in states) + ")"
        params.extend(states)
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM projectready_jobs{where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [_row(row, include_payload=False) or {} for row in rows]
