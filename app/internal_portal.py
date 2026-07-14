from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.database import get_conn
from app.jobs.store import cancel_job, get_job, init_job_tables, list_jobs, retry_job
from app.payments.internal_access import internal_access_configured, issue_internal_access, validate_internal_access

BASE_DIR = Path(__file__).resolve().parent
INTERNAL_ASSET_DIR = BASE_DIR / "internal_assets"
PUBLIC_STATIC_DIR = BASE_DIR / "static"
COOKIE_NAME = "pr_internal_portal_session"


def _portal_path() -> str:
    raw = str(os.getenv("PROJECTREADY_INTERNAL_PORTAL_PATH") or "").strip()
    if not raw:
        seed = str(
            os.getenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET")
            or os.getenv("SECRET_KEY")
            or os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256")
            or os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY")
            or "portal-disabled"
        )
        suffix = hashlib.sha256(("projectready-portal:" + seed).encode("utf-8")).hexdigest()[:18]
        raw = f"/internal/pr-ops-{suffix}"
    if not raw.startswith("/"):
        raw = "/" + raw
    if not re.fullmatch(r"/[A-Za-z0-9/_-]{10,120}", raw):
        raise RuntimeError("PROJECTREADY_INTERNAL_PORTAL_PATH must be a private path containing only letters, numbers, slashes, underscores and hyphens.")
    return raw.rstrip("/")


PORTAL_PATH = _portal_path()
router = APIRouter(include_in_schema=False)


def _require_configured() -> None:
    if not internal_access_configured():
        raise HTTPException(status_code=404, detail="Resource not found.")


def _portal_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Robots-Tag": "noindex, nofollow, noarchive",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        "Referrer-Policy": "no-referrer",
    }


class InternalLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    key: str = Field(min_length=6, max_length=6)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).replace(microsecond=0).isoformat()


def _hash(value: str) -> str:
    secret = str(os.getenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET") or os.getenv("SECRET_KEY") or "projectready")
    return hashlib.sha256((secret + ":" + str(value or "")).encode("utf-8")).hexdigest()


def init_internal_portal_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projectready_internal_login_audit (
                id TEXT PRIMARY KEY,
                identity_hash TEXT NOT NULL,
                ip_hash TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_internal_login_identity ON projectready_internal_login_audit(identity_hash, created_at)")
        conn.commit()


def _client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return str(request.client.host if request.client else "unknown")


def _failure_count(email: str, request: Request) -> int:
    init_internal_portal_tables()
    cutoff = _iso(_now() - timedelta(minutes=max(5, int(os.getenv("PROJECTREADY_INTERNAL_LOGIN_WINDOW_MINUTES", "15") or 15))))
    identity = _hash(str(email or "").strip().lower())
    ip_hash = _hash(_client_ip(request))
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total FROM projectready_internal_login_audit
            WHERE success=0 AND created_at >= ? AND (identity_hash=? OR ip_hash=?)
            """,
            (cutoff, identity, ip_hash),
        ).fetchone()
    return int(dict(row).get("total") or 0) if row else 0


def _record_attempt(email: str, request: Request, success: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO projectready_internal_login_audit(id, identity_hash, ip_hash, success, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), _hash(str(email or "").strip().lower()), _hash(_client_ip(request)), 1 if success else 0, _iso()),
        )
        conn.commit()


def _cookie_value(purchase_id: str, token: str) -> str:
    return json.dumps({"purchase_id": purchase_id, "access_token": token}, separators=(",", ":"))


def _read_session(request: Request) -> dict[str, Any]:
    raw = str(request.cookies.get(COOKIE_NAME) or "")
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise PermissionError("Internal session unavailable.") from exc
    purchase_id = str(data.get("purchase_id") or "")
    access_token = str(data.get("access_token") or "")
    if not purchase_id or not access_token:
        raise PermissionError("Internal session unavailable.")
    validated = validate_internal_access(
        purchase_id=purchase_id,
        access_token=access_token,
        product_area="all",
    )
    return {**validated, "purchase_id": purchase_id, "access_token": access_token}


def internal_session_or_none(request: Request) -> dict[str, Any] | None:
    try:
        return _read_session(request)
    except Exception:
        return None


def _secure_cookie(request: Request) -> bool:
    configured = str(os.getenv("PROJECTREADY_COOKIE_SECURE", "auto")).strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return str(request.url.scheme).lower() == "https"


@router.get(PORTAL_PATH)
def internal_portal_page() -> HTMLResponse:
    _require_configured()
    html = (INTERNAL_ASSET_DIR / "portal.html").read_text(encoding="utf-8").replace("{{PORTAL_PATH}}", PORTAL_PATH)
    return HTMLResponse(
        html,
        headers=_portal_headers(),
    )


@router.get(PORTAL_PATH + "/portal.css")
def internal_portal_css() -> FileResponse:
    _require_configured()
    return FileResponse(
        INTERNAL_ASSET_DIR / "portal.css",
        media_type="text/css",
        headers=_portal_headers(),
    )


@router.get(PORTAL_PATH + "/portal.js")
def internal_portal_javascript() -> FileResponse:
    _require_configured()
    return FileResponse(
        INTERNAL_ASSET_DIR / "portal.js",
        media_type="application/javascript",
        headers=_portal_headers(),
    )


@router.get(PORTAL_PATH + "/module-session.js")
def internal_module_session_javascript(request: Request) -> FileResponse:
    if not internal_session_or_none(request):
        raise HTTPException(status_code=404, detail="Resource not found.")
    return FileResponse(
        INTERNAL_ASSET_DIR / "module_session.js",
        media_type="application/javascript",
        headers=_portal_headers(),
    )


def _internal_module_page(request: Request, filename: str, module_script: str) -> HTMLResponse:
    if not internal_session_or_none(request):
        raise HTTPException(status_code=404, detail="Resource not found.")
    html = (PUBLIC_STATIC_DIR / filename).read_text(encoding="utf-8")
    bootstrap = f'<script src="{PORTAL_PATH}/module-session.js?v=20260714-commercial-v3"></script>\n  '
    target = f'<script src="/static/{module_script}'
    if target not in html:
        raise HTTPException(status_code=500, detail="Internal module page is unavailable.")
    html = html.replace(target, bootstrap + target, 1)
    return HTMLResponse(html, headers=_portal_headers())


@router.get(PORTAL_PATH + "/workspace")
def internal_workspace_page(request: Request) -> HTMLResponse:
    return _internal_module_page(request, "workspace.html", "app.js")


@router.get(PORTAL_PATH + "/chapter-strengthener")
def internal_strengthener_page(request: Request) -> HTMLResponse:
    return _internal_module_page(request, "chapter_strengthener.html", "projectready_payments.js")


@router.get(PORTAL_PATH + "/topic-ideas")
def internal_topic_ideas_page(request: Request) -> HTMLResponse:
    return _internal_module_page(request, "topic_ideas.html", "topic_ideas.js")


@router.post(PORTAL_PATH + "/api/session")
@router.post("/api/internal/session")
def create_internal_session(payload: InternalLoginRequest, request: Request) -> JSONResponse:
    _require_configured()
    maximum = max(3, min(int(os.getenv("PROJECTREADY_INTERNAL_LOGIN_MAX_ATTEMPTS", "5") or 5), 12))
    if _failure_count(payload.email, request) >= maximum:
        raise HTTPException(status_code=429, detail="Access is temporarily unavailable.")
    try:
        access = issue_internal_access(email=payload.email, key=payload.key, product_area="all")
    except Exception:
        _record_attempt(payload.email, request, False)
        # Do not disclose whether the email or key was incorrect.
        raise HTTPException(status_code=404, detail="Access is unavailable.")
    _record_attempt(payload.email, request, True)
    response = JSONResponse({
        "ok": True,
        "message": "Restricted internal session activated.",
        "portal_path": PORTAL_PATH,
        "expires_at": access.get("expires_at"),
    })
    max_age = max(3600, int(access.get("validity_hours") or 12) * 3600)
    response.set_cookie(
        COOKIE_NAME,
        _cookie_value(str(access.get("purchase_id") or ""), str(access.get("access_token") or "")),
        max_age=max_age,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="strict",
        path="/",
    )
    return response


@router.get(PORTAL_PATH + "/api/session")
@router.get("/api/internal/session")
def internal_session_status(request: Request) -> dict[str, Any]:
    session = internal_session_or_none(request)
    if not session:
        raise HTTPException(status_code=404, detail="Session unavailable.")
    email = str(session.get("email") or "")
    masked = email[:2] + "***" + email[email.find("@"):] if "@" in email else "internal"
    return {
        "ok": True,
        "active": True,
        "email": masked,
        "expires_at": session.get("expires_at_epoch"),
        "portal_path": PORTAL_PATH,
    }


@router.delete(PORTAL_PATH + "/api/session")
@router.delete("/api/internal/session")
def close_internal_session(request: Request) -> Response:
    response = JSONResponse({"ok": True, "message": "Restricted internal session closed."})
    response.delete_cookie(COOKIE_NAME, path="/", secure=_secure_cookie(request), samesite="strict")
    return response


@router.post(PORTAL_PATH + "/api/module-access")
@router.post("/api/internal/module-access")
def internal_module_access(request: Request) -> dict[str, Any]:
    session = internal_session_or_none(request)
    if not session:
        raise HTTPException(status_code=404, detail="Access unavailable.")
    return {
        "ok": True,
        "purchase_id": session.get("purchase_id"),
        "access_token": session.get("access_token"),
        "provider": "internal_admin",
        "product_area": "all",
        "chapter_number": 0,
        "message": "Restricted internal access is active.",
    }


@router.get(PORTAL_PATH + "/api/jobs")
@router.get("/api/internal/jobs")
def internal_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    if not internal_session_or_none(request):
        raise HTTPException(status_code=404, detail="Resource not found.")
    init_job_tables()
    return {"ok": True, "jobs": list_jobs(limit=limit)}


@router.post(PORTAL_PATH + "/api/jobs/{job_id}/cancel")
@router.post("/api/internal/jobs/{job_id}/cancel")
def internal_cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    if not internal_session_or_none(request):
        raise HTTPException(status_code=404, detail="Resource not found.")
    job = get_job(job_id, include_payload=True)
    if not job:
        raise HTTPException(status_code=404, detail="Resource not found.")
    if str(job.get("status")) == "running":
        raise HTTPException(status_code=409, detail="A running job cannot be cancelled safely.")
    return {"ok": True, "job": cancel_job(job_id)}


@router.post(PORTAL_PATH + "/api/jobs/{job_id}/retry")
@router.post("/api/internal/jobs/{job_id}/retry")
def internal_retry_job(job_id: str, request: Request) -> dict[str, Any]:
    if not internal_session_or_none(request):
        raise HTTPException(status_code=404, detail="Resource not found.")
    job = get_job(job_id, include_payload=True)
    if not job:
        raise HTTPException(status_code=404, detail="Resource not found.")
    claim = (job.get("payload") or {}).get("_preauthorized_claim") or {}
    if claim.get("claimed") and not claim.get("internal_access"):
        raise HTTPException(status_code=409, detail="A paid failed job must be resubmitted by the user so a fresh entitlement can be reserved.")
    return {"ok": True, "job": retry_job(job_id)}
