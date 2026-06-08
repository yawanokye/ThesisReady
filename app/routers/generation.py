from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.ai_service import generate_chapter
from app.compliance import check_chapter
from app.database import get_conn, row_to_dict
from app.export import export_chapter_docx, export_compliance_docx
from app.result_uploads import extract_result_file
from app.schemas import ComplianceRequest, DraftRequest
from app.template_store import get_chapter

router = APIRouter(prefix="/api/projects", tags=["generation"])
EXPORT_DIR = Path("exports")

FREE_PLAN_NAMES = {"free", "free starter", "starter"}
FREE_CHAPTER_NUMBER = 1
FREE_ALLOWED_SECTION_IDS = {
    "ch1_background",
    "ch1_problem",
    "ch1_purpose",
    "ch1_objectives",
    "ch1_questions",
}


def _is_free_plan(profile: dict[str, Any]) -> bool:
    plan = str(profile.get("access_plan") or "Free Starter").strip().lower()
    return plan in FREE_PLAN_NAMES


def _enforce_free_plan(profile: dict[str, Any], chapter_number: int, selected_section_ids: list[str], revision_mode: bool = False) -> None:
    if not _is_free_plan(profile):
        return
    if chapter_number != FREE_CHAPTER_NUMBER:
        raise HTTPException(
            status_code=403,
            detail="Free Starter allows drafting only for the first five sections of Chapter One. Please upgrade to draft other chapters.",
        )
    disallowed = [section_id for section_id in selected_section_ids if section_id not in FREE_ALLOWED_SECTION_IDS]
    if disallowed or len(selected_section_ids) > len(FREE_ALLOWED_SECTION_IDS):
        raise HTTPException(
            status_code=403,
            detail="Free Starter allows only these Chapter One sections: Background, Statement of the Problem, Purpose, Research Objectives, and Research Questions.",
        )
    if revision_mode:
        raise HTTPException(
            status_code=403,
            detail="Revised-version upload and guided revision are available on paid plans.",
        )


def _uploaded_revision_source(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    uploaded = profile.get("uploaded_chapter_sources") or {}
    return uploaded.get(str(chapter_number)) or {}


@router.post("/{project_id}/draft")
def draft_chapter(project_id: str, payload: DraftRequest):
    project = _get_project_or_404(project_id)
    try:
        chapter = get_chapter(payload.chapter_number)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _enforce_free_plan(
        project.get("profile", {}),
        payload.chapter_number,
        payload.selected_section_ids,
        revision_mode=payload.revision_mode,
    )

    if payload.revision_mode and not _uploaded_revision_source(project.get("profile", {}), payload.chapter_number):
        raise HTTPException(status_code=400, detail="Please upload the existing chapter before generating a revised version.")

    draft, source = generate_chapter(
        profile=project["profile"],
        chapter_number=payload.chapter_number,
        selected_section_ids=payload.selected_section_ids,
        answers=payload.answers,
        extra_instructions=payload.extra_instructions,
        use_ai=payload.use_ai,
        revision_mode=payload.revision_mode,
        revision_instructions=payload.revision_instructions,
    )

    drafts = project.get("drafts", {})
    drafts[str(payload.chapter_number)] = draft
    selected = project.get("selected_sections", {})
    selected[str(payload.chapter_number)] = payload.selected_section_ids

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projects
            SET drafts_json = ?, selected_sections_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(drafts), json.dumps(selected), project_id),
        )
        conn.commit()

    return {
        "chapter_number": payload.chapter_number,
        "chapter_title": chapter.get("chapter_title"),
        "draft": draft,
        "source": source,
    }


@router.post("/{project_id}/upload-chapter")
async def upload_chapter_for_revision(
    project_id: str,
    file: UploadFile = File(...),
    chapter_number: int = Form(...),
):
    """Upload an existing chapter so ProjectReady AI can revise it.

    The extracted content is saved inside profile["uploaded_chapter_sources"][chapter_number].
    When revision mode is selected, the drafting engine uses this text as the base chapter and
    marks new insertions with red change markers in the preview and DOCX export.
    """
    project = _get_project_or_404(project_id)
    profile = project.get("profile", {})
    if _is_free_plan(profile):
        raise HTTPException(status_code=403, detail="Chapter revision upload is available on paid plans.")

    filename = file.filename or "chapter_upload"
    contents = await file.read()
    try:
        extracted = extract_result_file(filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process uploaded chapter: {exc}") from exc

    uploaded_sources = profile.get("uploaded_chapter_sources") or {}
    uploaded_sources[str(chapter_number)] = {
        **extracted,
        "content_type": file.content_type or "",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "chapter_number": chapter_number,
        "purpose": "chapter_revision_source",
    }
    profile["uploaded_chapter_sources"] = uploaded_sources

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "filename": extracted["filename"],
        "file_type": extracted["file_type"],
        "characters_extracted": extracted["characters_extracted"],
        "truncated": extracted["truncated"],
        "preview": extracted["preview"],
        "message": "Chapter uploaded and attached as the revision source.",
    }


@router.post("/{project_id}/upload-results")
async def upload_results(
    project_id: str,
    file: UploadFile = File(...),
    chapter_number: int = Form(4),
):
    """Upload result output so Chapter Four can use it during drafting.

    The extracted content is saved inside the project profile under
    profile["uploaded_results"][chapter_number]. This avoids a database
    migration while still making the content available to the drafting prompt.
    """
    project = _get_project_or_404(project_id)

    filename = file.filename or "results_upload"
    contents = await file.read()
    try:
        extracted = extract_result_file(filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process uploaded file: {exc}") from exc

    profile = project.get("profile", {})
    uploaded_results = profile.get("uploaded_results") or {}
    uploaded_results[str(chapter_number)] = {
        **extracted,
        "content_type": file.content_type or "",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "chapter_number": chapter_number,
    }
    profile["uploaded_results"] = uploaded_results

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "filename": extracted["filename"],
        "file_type": extracted["file_type"],
        "characters_extracted": extracted["characters_extracted"],
        "truncated": extracted["truncated"],
        "preview": extracted["preview"],
        "message": "Results uploaded and attached to the project profile.",
    }


@router.post("/{project_id}/check")
def run_compliance_check(project_id: str, payload: ComplianceRequest):
    project = _get_project_or_404(project_id)
    _enforce_free_plan(project.get("profile", {}), payload.chapter_number, payload.selected_section_ids)

    draft = payload.draft or project.get("drafts", {}).get(str(payload.chapter_number), "")
    if not draft.strip():
        raise HTTPException(status_code=400, detail="No draft found for this chapter")

    check = check_chapter(payload.chapter_number, payload.selected_section_ids, draft)
    checks = project.get("checks", {})
    checks[str(payload.chapter_number)] = check

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET checks_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(checks), project_id),
        )
        conn.commit()

    return check


@router.get("/{project_id}/export/chapter/{chapter_number}")
def export_chapter(project_id: str, chapter_number: int):
    project = _get_project_or_404(project_id)
    if _is_free_plan(project.get("profile", {})) and chapter_number != FREE_CHAPTER_NUMBER:
        raise HTTPException(status_code=403, detail="Free Starter exports are limited to Chapter One.")
    draft = project.get("drafts", {}).get(str(chapter_number), "")
    if not draft.strip():
        raise HTTPException(status_code=400, detail="No draft found for this chapter")
    path = export_chapter_docx(project, chapter_number, draft, EXPORT_DIR)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/{project_id}/export/check/{chapter_number}")
def export_check(project_id: str, chapter_number: int):
    project = _get_project_or_404(project_id)
    if _is_free_plan(project.get("profile", {})) and chapter_number != FREE_CHAPTER_NUMBER:
        raise HTTPException(status_code=403, detail="Free Starter compliance exports are limited to Chapter One.")
    check = project.get("checks", {}).get(str(chapter_number))
    if not check:
        raise HTTPException(status_code=400, detail="No compliance report found for this chapter")
    path = export_compliance_docx(project, chapter_number, check, EXPORT_DIR)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
