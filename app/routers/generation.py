from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.ai_service import generate_chapter
from app.compliance import check_chapter
from app.database import get_conn, row_to_dict
from app.export import export_chapter_docx, export_compliance_docx, export_instrument_docx, export_methods_supplement_docx
from app.result_uploads import extract_result_file
from app.schemas import ComplianceRequest, DraftRequest
from app.template_store import get_chapter

router = APIRouter(prefix="/api/projects", tags=["generation"])
EXPORT_DIR = Path("exports")



def _source_key(src: dict[str, Any]) -> str:
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:100]
    return "title:" + title


def _merge_sources(existing: list[dict[str, Any]], new_sources: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in [*(existing or []), *(new_sources or [])]:
        if not isinstance(src, dict):
            continue
        key = _source_key(src)
        if not key or key == "title:" or key in seen:
            continue
        seen.add(key)
        merged.append(src)
        if len(merged) >= limit:
            break
    return merged


def _merge_payload_sources_into_profile(profile: dict[str, Any], payload: DraftRequest) -> dict[str, Any]:
    """Make source-search results available to the drafting prompt even if the DB update
    was missed, stale, or the frontend generated immediately after source search."""
    incoming_bank = getattr(payload, "source_bank", None) or []
    incoming_retrieved = getattr(payload, "retrieved_sources", None) or {}
    if isinstance(incoming_retrieved, dict):
        incoming_bank = _merge_sources(incoming_bank, incoming_retrieved.get("sources") or [])

    existing_bank = profile.get("source_bank") or []
    if not isinstance(existing_bank, list):
        existing_bank = []

    merged_bank = _merge_sources(existing_bank, incoming_bank)
    if merged_bank:
        profile["source_bank"] = merged_bank
        if isinstance(incoming_retrieved, dict) and incoming_retrieved:
            current_retrieved = profile.get("retrieved_sources") or {}
            current_sources = current_retrieved.get("sources") or [] if isinstance(current_retrieved, dict) else []
            profile["retrieved_sources"] = {
                **(current_retrieved if isinstance(current_retrieved, dict) else {}),
                **incoming_retrieved,
                "sources": _merge_sources(current_sources, incoming_retrieved.get("sources") or merged_bank),
                "source_bank_count": len(merged_bank),
            }
        elif not profile.get("retrieved_sources"):
            profile["retrieved_sources"] = {"sources": merged_bank, "source_bank_count": len(merged_bank)}

    source_terms = getattr(payload, "source_search_terms", "") or ""
    if source_terms:
        profile["source_search_terms"] = source_terms
    return profile

@router.post("/{project_id}/draft")
def draft_chapter(project_id: str, payload: DraftRequest):
    project = _get_project_or_404(project_id)
    try:
        chapter = get_chapter(payload.chapter_number)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Some deployed frontends include revision-mode fields. Use getattr defaults so
    # the endpoint remains stable even when schemas and frontend files are updated
    # at different times.
    revision_mode = bool(getattr(payload, "revision_mode", False))
    revision_text = (
        getattr(payload, "revision_text", "")
        or getattr(payload, "existing_chapter_text", "")
        or getattr(payload, "uploaded_revision_text", "")
        or ""
    )
    if not revision_text.strip():
        uploaded_revisions = (project.get("profile", {}) or {}).get("uploaded_revisions") or {}
        uploaded_revision = uploaded_revisions.get(str(payload.chapter_number)) or {}
        revision_text = uploaded_revision.get("extracted_text", "") or revision_text
        if uploaded_revision and not getattr(payload, "revision_filename", ""):
            try:
                payload.revision_filename = uploaded_revision.get("filename", "")
            except Exception:
                pass
    revision_instructions = getattr(payload, "revision_instructions", "") or ""
    extra_instructions = payload.extra_instructions or ""

    if revision_mode:
        revision_parts = [
            "Revision mode is enabled. Revise the uploaded chapter rather than drafting from scratch.",
            "Retain accurate content, improve scholarly flow, correct tense, align with the selected guideline sections, and do not invent new sources, statistics, findings, or approvals.",
            "Preserve the uploaded chapter's existing argument and structure unless the revision instruction asks for restructuring.",
            "Mark substantive new insertions with [[ADD]] and [[/ADD]] so the DOCX export can colour additions red. Do not mark unchanged original text as an addition.",
            "Where helpful, include brief revision comments as bracketed comments such as [Revision comment: ...] without interrupting the academic flow.",
        ]
        if revision_instructions.strip():
            revision_parts.append(f"Revision instructions: {revision_instructions.strip()}")
        if revision_text.strip():
            revision_parts.append("Existing chapter text to revise:\n" + revision_text.strip())
        extra_instructions = (extra_instructions + "\n\n" + "\n\n".join(revision_parts)).strip()

    project["profile"] = _merge_payload_sources_into_profile(project.get("profile", {}), payload)

    # Merge human contribution and writing-style controls from the current draft request.
    incoming_contribution = getattr(payload, "student_contribution", None) or {}
    if isinstance(incoming_contribution, dict):
        existing_contribution = project["profile"].get("student_contribution") or {}
        if not isinstance(existing_contribution, dict):
            existing_contribution = {}
        merged_contribution = {**existing_contribution, **incoming_contribution}
        project["profile"]["student_contribution"] = merged_contribution
        project["profile"]["draft_maturity"] = merged_contribution.get("draft_maturity") or getattr(payload, "draft_maturity", "") or project["profile"].get("draft_maturity", "Supervisor-ready draft")
        if getattr(payload, "human_revision_pass", None) is not None:
            merged_contribution["human_revision_pass"] = bool(getattr(payload, "human_revision_pass", True))

    contribution = project["profile"].get("student_contribution") or {}
    if isinstance(contribution, dict) and any(str(contribution.get(k) or "").strip() for k in ["central_argument", "local_context_notes", "evidence_anchors", "supervisor_comments", "preferred_style", "writing_sample"]):
        human_parts = ["Student contribution and writing-style controls supplied. Use them to improve academic specificity and natural scholarly flow; do not add a visible AI or detector note to the chapter."]
        for label, key in [
            ("Central argument", "central_argument"),
            ("Local context notes", "local_context_notes"),
            ("Evidence anchors", "evidence_anchors"),
            ("Supervisor comments", "supervisor_comments"),
            ("Preferred style / phrases to avoid", "preferred_style"),
            ("Writing sample for tone guidance", "writing_sample"),
        ]:
            value = str(contribution.get(key) or "").strip()
            if value:
                human_parts.append(f"{label}: {value}")
        extra_instructions = (extra_instructions + "\n\n" + "\n".join(human_parts)).strip()

    other_title = getattr(payload, "other_chapter_title", "") or project["profile"].get("other_chapter_title", "")
    other_instructions = getattr(payload, "other_chapter_instructions", "") or project["profile"].get("other_chapter_instructions", "")
    if payload.chapter_number == 6 and (other_title or other_instructions):
        project["profile"]["other_chapter_title"] = other_title
        project["profile"]["other_chapter_instructions"] = other_instructions
        extra_instructions = (extra_instructions + "\n\n" + f"Other chapter title: {other_title}\nUser-specified chapter requirements: {other_instructions}").strip()

    generation_warning = ""
    try:
        draft, source = generate_chapter(
            profile=project["profile"],
            chapter_number=payload.chapter_number,
            selected_section_ids=payload.selected_section_ids,
            answers=payload.answers,
            extra_instructions=extra_instructions,
            use_ai=payload.use_ai,
        )
    except Exception as exc:
        # Never let a provider timeout, stale frontend payload, custom chapter, or
        # unexpected section ID produce a generic Internal Server Error. Return a
        # usable local draft and surface a clear warning to the frontend.
        generation_warning = f"AI generation could not complete safely; a structured local fallback was returned. Details: {str(exc)[:180]}"
        draft, source = generate_chapter(
            profile=project["profile"],
            chapter_number=payload.chapter_number,
            selected_section_ids=payload.selected_section_ids,
            answers=payload.answers,
            extra_instructions=extra_instructions,
            use_ai=False,
        )
        source = source + "_after_error"

    drafts = project.get("drafts", {})
    drafts[str(payload.chapter_number)] = draft
    selected = project.get("selected_sections", {})
    selected[str(payload.chapter_number)] = payload.selected_section_ids

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projects
            SET profile_json = ?, drafts_json = ?, selected_sections_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(project.get("profile", {})), json.dumps(drafts), json.dumps(selected), project_id),
        )
        conn.commit()

    return {
        "chapter_number": payload.chapter_number,
        "chapter_title": chapter.get("chapter_title"),
        "draft": draft,
        "source": source,
        "warning": generation_warning,
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


@router.post("/{project_id}/upload-revision")
async def upload_revision(
    project_id: str,
    file: UploadFile = File(...),
    chapter_number: int = Form(1),
):
    """Upload an existing chapter for revision.

    The original text is extracted and stored under profile["uploaded_revisions"].
    During draft generation, the frontend can also send this text in revision_text.
    """
    project = _get_project_or_404(project_id)
    filename = file.filename or "chapter_revision_upload"
    contents = await file.read()
    try:
        extracted = extract_result_file(filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process uploaded revision file: {exc}") from exc

    profile = project.get("profile", {})
    uploaded_revisions = profile.get("uploaded_revisions") or {}
    uploaded_revisions[str(chapter_number)] = {
        **extracted,
        "content_type": file.content_type or "",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "chapter_number": chapter_number,
    }
    profile["uploaded_revisions"] = uploaded_revisions

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
        "extracted_text": extracted["extracted_text"],
        "message": "Revision file uploaded and attached to the project profile.",
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


@router.get("/{project_id}/export/instrument/{chapter_number}")
def export_instrument(project_id: str, chapter_number: int):
    project = _get_project_or_404(project_id)
    if chapter_number != 3:
        raise HTTPException(status_code=400, detail="Draft instruments are available for the Research Methods/Methodology chapter only.")
    profile = project.get("profile", {})
    data_type = str(profile.get("data_type") or "").lower()
    approach = str(profile.get("research_approach") or "").lower()
    if not any(key in data_type for key in ["primary", "survey", "qualitative", "mixed"]) and not any(key in approach for key in ["quantitative", "qualitative", "mixed"]):
        raise HTTPException(status_code=400, detail="Draft instruments are intended for primary survey, qualitative, or mixed-method studies.")
    path = export_instrument_docx(project, chapter_number, EXPORT_DIR)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")




@router.get("/{project_id}/export/methods-supplement")
def export_methods_supplement(project_id: str):
    project = _get_project_or_404(project_id)
    # This is intentionally independent of the selected chapter. The main
    # Research Methods/Methodology chapter remains a submission-ready chapter,
    # while this supplementary chapter gathers instruments, measurement details,
    # variable/data-source registers and appendix materials for analysis.
    path = export_methods_supplement_docx(project, 0, EXPORT_DIR)
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
