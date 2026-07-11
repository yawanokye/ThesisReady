from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from app.database import get_conn, row_to_dict
from app.project_recovery import recover_projects, recovery_enabled, set_project_recovery
from app.result_uploads import extract_result_file
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


def _normalise_lines(value: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for line in str(value or "").splitlines():
        line = line.strip()
        line = re.sub(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\s*[.)-]\s*", "", line, flags=re.I).strip()
        if len(line) < 4:
            continue
        key = line.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(line)
    return cleaned[:12]


def _section_text(text: str, heading_patterns: list[str], stop_patterns: list[str] | None = None, limit: int = 2500) -> str:
    source = str(text or "")
    starts: list[int] = []
    for pattern in heading_patterns:
        match = re.search(pattern, source, flags=re.I | re.M)
        if match:
            starts.append(match.end())
    if not starts:
        return ""
    start = min(starts)
    end = len(source)
    stops = stop_patterns or [
        r"^\s*\d+(?:\.\d+)*\s+", r"^\s*CHAPTER\s+", r"^\s*References\s*$",
    ]
    for pattern in stops:
        stop = re.search(pattern, source[start:], flags=re.I | re.M)
        if stop and stop.start() > 30:
            end = min(end, start + stop.start())
    return source[start:end].strip()[:limit]


def _extract_numbered_items_after_heading(text: str, heading_patterns: list[str], limit: int = 10) -> list[str]:
    block = _section_text(text, heading_patterns, limit=5000)
    if not block:
        return []
    items: list[str] = []
    current: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\s*[.)-]\s+", stripped, flags=re.I):
            if current:
                items.append(" ".join(current).strip())
            current = [re.sub(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\s*[.)-]\s+", "", stripped, flags=re.I).strip()]
        elif current and not re.match(r"^\s*\d+(?:\.\d+)*\s+", stripped):
            current.append(stripped)
    if current:
        items.append(" ".join(current).strip())
    return _normalise_lines("\n".join(items))[:limit]


def _guess_title(text: str, filename: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    skip = re.compile(r"^(chapter\s+one|introduction|references|source use audit|responsible-use notice|chapter\s+1\b)", re.I)
    for line in lines[:20]:
        if skip.search(line):
            continue
        if 8 <= len(line) <= 180 and not line.endswith("."):
            return line.strip().title() if line.islower() else line.strip()
    return Path(filename or "").stem.replace("_", " ").replace("-", " ").strip().title()


def _profile_suggestions_from_chapter_one(text: str, filename: str) -> dict[str, Any]:
    title = _guess_title(text, filename)
    objectives = _extract_numbered_items_after_heading(
        text,
        [r"^\s*(?:\d+(?:\.\d+)*\s*)?(?:specific\s+)?research\s+objectives\s*$", r"^\s*(?:\d+(?:\.\d+)*\s*)?specific\s+objectives\s*$"],
        limit=10,
    )
    questions = _extract_numbered_items_after_heading(
        text,
        [r"^\s*(?:\d+(?:\.\d+)*\s*)?research\s+questions\s*$"],
        limit=10,
    )
    background = _section_text(
        text,
        [r"^\s*(?:\d+(?:\.\d+)*\s*)?background\s+to\s+the\s+study\s*$", r"^\s*(?:\d+(?:\.\d+)*\s*)?background\s*$"],
        limit=1200,
    )
    problem = _section_text(
        text,
        [r"^\s*(?:\d+(?:\.\d+)*\s*)?statement\s+of\s+the\s+problem\s*$", r"^\s*(?:\d+(?:\.\d+)*\s*)?problem\s+statement\s*$"],
        limit=1200,
    )
    context = "\n\n".join(part for part in [background, problem] if part).strip()
    if not context:
        context = " ".join(str(text or "").split()[:180])

    research_area = ""
    lower_title = title.lower()
    if " among " in lower_title:
        research_area = title[: lower_title.index(" among ")].strip()
    elif " in " in lower_title:
        research_area = title[: lower_title.index(" in ")].strip()
    else:
        research_area = title[:90].strip()

    variable_candidates: list[str] = []
    for phrase in re.split(r"\s+(?:and|among|in|within|of|on)\s+", title, flags=re.I):
        phrase = phrase.strip(" ,.;:-")
        if 3 <= len(phrase) <= 80 and not re.search(r"ghana|cape coast|university|workers|students|sector", phrase, re.I):
            variable_candidates.append(phrase)

    return {
        "title": title,
        "research_area": research_area,
        "study_context": context,
        "objectives": objectives,
        "research_questions": questions,
        "variables": _normalise_lines("\n".join(variable_candidates))[:8],
    }


@router.post("/extract-introduction-profile")
async def extract_introduction_profile(file: UploadFile = File(...)):
    filename = file.filename or "chapter_one_upload"
    contents = await file.read()
    try:
        extracted = extract_result_file(filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    text = str(extracted.get("extracted_text") or "")
    suggestions = _profile_suggestions_from_chapter_one(text, filename)
    return {
        "filename": extracted.get("filename") or filename,
        "characters_extracted": extracted.get("characters_extracted", len(text)),
        "truncated": extracted.get("truncated", False),
        "profile_suggestions": suggestions,
        "preview": extracted.get("preview") or text[:1800],
        "message": "Introduction/Chapter One extracted. Review all autofilled fields before drafting.",
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
