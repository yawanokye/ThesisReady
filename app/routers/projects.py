from __future__ import annotations

import json
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.database import get_conn, row_to_dict
from app.project_recovery import recover_projects, recovery_enabled, set_project_recovery
from app.payments.store import rotate_project_access_tokens
from app.schemas import (
    ProjectCreate,
    ProjectRecoveryRequest,
    ProjectRecoverySetupRequest,
    SectionSelection,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_RECOVERY_WINDOW_SECONDS = max(
    60,
    int(os.getenv("PROJECTREADY_RECOVERY_WINDOW_SECONDS", "900")),
)
_RECOVERY_MAX_ATTEMPTS = max(
    3,
    int(os.getenv("PROJECTREADY_RECOVERY_MAX_ATTEMPTS", "6")),
)
_recovery_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_key(request: Request, email: str) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "unknown")
    return f"{client_ip}:{str(email or '').strip().lower()}"


def _check_recovery_rate_limit(request: Request, email: str) -> None:
    now = time.monotonic()
    key = _rate_limit_key(request, email)
    bucket = _recovery_attempts[key]
    while bucket and now - bucket[0] > _RECOVERY_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _RECOVERY_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many recovery attempts. Wait a few minutes and try again.",
        )
    bucket.append(now)


@router.post("")
def create_project(payload: ProjectCreate):
    if not payload.academic_integrity_confirmed or not payload.user_contribution_confirmed:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm the academic-integrity and user-contribution declarations "
                "before creating the research project."
            ),
        )
    project_id = str(uuid.uuid4())
    raw = payload.model_dump()
    recovery_email = str(raw.pop("recovery_email", "") or "").strip()
    recovery_pin = str(raw.pop("recovery_pin", "") or "").strip()
    profile = raw

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, title, profile_json, selected_sections_json, drafts_json, checks_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, payload.title, json.dumps(profile), "{}", "{}", "{}"),
        )
        conn.commit()

    recovery_was_enabled = False
    if recovery_email or recovery_pin:
        if not recovery_email or not recovery_pin:
            raise HTTPException(
                status_code=422,
                detail="Provide both the recovery email and the 6-digit recovery PIN.",
            )
        try:
            set_project_recovery(project_id, recovery_email, recovery_pin)
            recovery_was_enabled = True
        except ValueError as exc:
            with get_conn() as conn:
                conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.commit()
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "id": project_id,
        "title": payload.title,
        "profile": profile,
        "recovery_enabled": recovery_was_enabled,
    }


@router.get("")
def list_projects(x_projectready_admin_key: str = Header(default="")):
    """Administrative listing only. Public users recover projects with email and PIN."""
    configured = os.getenv("PROJECTREADY_ADMIN_KEY", "").strip()
    if not configured or x_projectready_admin_key != configured:
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [row_to_dict(row) for row in rows]


@router.post("/recover")
def recover_project_ids(payload: ProjectRecoveryRequest, request: Request):
    _check_recovery_rate_limit(request, payload.email)
    try:
        projects = recover_projects(payload.email, payload.recovery_pin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not projects:
        raise HTTPException(
            status_code=404,
            detail=(
                "No project matched those recovery details. Check the email and PIN, "
                "or use the browser where the project was created."
            ),
        )

    restored_access: list[dict[str, Any]] = []
    for project in projects:
        credentials = rotate_project_access_tokens(str(project.get("id") or ""))
        project["restored_purchase_count"] = len(credentials)
        restored_access.extend(credentials)
    return {
        "recovered": True,
        "count": len(projects),
        "projects": projects,
        "restored_access": restored_access,
        "access_note": (
            "Active paid chapter credentials were renewed for this browser. "
            "Older browser credentials for the same purchases are no longer valid."
            if restored_access
            else "No active paid chapter credential required renewal."
        ),
    }


@router.post("/{project_id}/recovery")
def configure_project_recovery(project_id: str, payload: ProjectRecoverySetupRequest):
    _get_project_or_404(project_id)
    try:
        result = set_project_recovery(project_id, payload.email, payload.recovery_pin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **result,
        "message": "Project recovery has been enabled. Keep the email and PIN private.",
    }


@router.get("/{project_id}")
def get_project(project_id: str):
    project = _get_project_or_404(project_id)
    project["recovery_enabled"] = recovery_enabled(project_id)
    return project


@router.post("/{project_id}/sections")
def save_section_selection(project_id: str, payload: SectionSelection):
    project = _get_project_or_404(project_id)
    selected = project.get("selected_sections", {})
    selected[str(payload.chapter_number)] = payload.selected_section_ids
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET selected_sections_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(selected), project_id),
        )
        conn.commit()
    return {"project_id": project_id, "selected_sections": selected}


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
