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


@router.post("/{project_id}/draft")
def draft_chapter(project_id: str, payload: DraftRequest):
    project = _get_project_or_404(project_id)
    try:
        chapter = get_chapter(payload.chapter_number)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    draft, source = generate_chapter(
        profile=project["profile"],
        chapter_number=payload.chapter_number,
        selected_section_ids=payload.selected_section_ids,
        answers=payload.answers,
        extra_instructions=payload.extra_instructions,
        use_ai=payload.use_ai,
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
    draft = project.get("drafts", {}).get(str(chapter_number), "")
    if not draft.strip():
        raise HTTPException(status_code=400, detail="No draft found for this chapter")
    path = export_chapter_docx(project, chapter_number, draft, EXPORT_DIR)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/{project_id}/export/check/{chapter_number}")
def export_check(project_id: str, chapter_number: int):
    project = _get_project_or_404(project_id)
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
