from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.chapter_file_extractor import extract_uploaded_text
from app.chapter_revision_service import (
    chapter_planning_targets,
    export_revised_chapter_docx,
    revise_chapter,
)
from app.database import get_conn, row_to_dict
from app.project_recovery import set_project_recovery
from app.payments.guard import (
    PaymentRequiredError,
    credentials_from_headers,
    paid_chapter_action,
)
from app.schemas import (
    ChapterRevisionExportRequest,
    ChapterRevisionRequest,
    ChapterTargetRequest,
    ExternalRevisionProjectCreate,
)

router = APIRouter(tags=["ProjectReady AI Chapter Strengthener"])


def _project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _chapter_number(chapter_type: str) -> int:
    value = str(chapter_type or "").strip()
    if value and value[0].isdigit():
        number = int(value[0])
        if 1 <= number <= 5:
            return number
    return 6


def _chapter_title(chapter_type: str, custom_title: str = "") -> str:
    return str(custom_title or chapter_type or "Strengthened Thesis Chapter").strip()


def _payment_detail(message: str, action: str, chapter_number: int) -> dict[str, Any]:
    return {
        "code": "chapter_payment_required",
        "message": message,
        "action": action,
        "chapter_number": chapter_number,
        "checkout_endpoint": "/api/payments/checkout",
    }


def _paid_context(
    request: Request,
    *,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    action: str,
):
    credentials = credentials_from_headers(request.headers)
    return paid_chapter_action(
        purchase_id=credentials["purchase_id"],
        access_token=credentials["access_token"],
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        action=action,
        idempotency_key=request.headers.get("Idempotency-Key"),
        metadata={
            "route": request.url.path,
            "method": request.method,
            "module": "chapter_strengthener",
        },
    )


def _lines(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {item}" for key, item in value.items() if str(item).strip()
        )
    return str(value or "").strip()


def _merge_project_profile(payload: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    profile = project.get("profile") or {}
    merged = dict(payload)
    defaults = {
        "thesis_title": project.get("title") or profile.get("title"),
        "academic_level": profile.get("level"),
        "discipline": profile.get("programme") or profile.get("department"),
        "research_area": profile.get("research_area"),
        "context": profile.get("study_context"),
        "objectives": _lines(profile.get("objectives")),
        "research_questions": _lines(profile.get("research_questions")),
        "hypotheses": _lines(profile.get("hypotheses")),
        "variables_constructs": _lines(profile.get("variables")),
        "methodology": profile.get("research_approach"),
        "school_guidelines": profile.get("format_notes"),
        "source_search_terms": profile.get("source_search_terms"),
    }
    for key, value in defaults.items():
        if not str(merged.get(key) or "").strip() and str(value or "").strip():
            merged[key] = value

    existing_bank = profile.get("source_bank") or []
    supplied_bank = merged.get("source_bank") or []
    if isinstance(existing_bank, list) and isinstance(supplied_bank, list):
        combined: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*supplied_bank, *existing_bank]:
            if not isinstance(item, dict):
                continue
            identity = str(item.get("doi") or item.get("title") or "").strip().lower()
            if not identity or identity in seen:
                continue
            seen.add(identity)
            combined.append(item)
            if len(combined) >= 120:
                break
        merged["source_bank"] = combined

    chapter_number = _chapter_number(str(merged.get("chapter_type") or ""))
    if not str(merged.get("data_and_results") or "").strip():
        uploaded_results = profile.get("uploaded_results") or {}
        result_record = uploaded_results.get(str(chapter_number)) or {}
        merged["data_and_results"] = (
            result_record.get("extracted_text")
            or result_record.get("text")
            or ""
        )
    return merged


@router.post("/api/chapter-strengthener/extract-file")
async def extract_chapter_strengthener_file(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        content = await file.read()
        return extract_uploaded_text(file.filename or "upload", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"File extraction failed: {str(exc)[:240]}",
        ) from exc


@router.post("/api/chapter-strengthener/targets")
def chapter_strengthener_targets(payload: ChapterTargetRequest) -> dict[str, Any]:
    return chapter_planning_targets(payload.academic_level, payload.chapter_type)


@router.post("/api/chapter-strengthener/external-projects")
def create_external_revision_project(payload: ExternalRevisionProjectCreate) -> dict[str, Any]:
    """Create a lightweight project for a chapter written outside ProjectReady AI."""
    if not payload.academic_integrity_confirmed or not payload.user_contribution_confirmed:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm that the uploaded chapter is part of your own authorised academic work, "
                "that you supplied the underlying research materials, and that you will independently review the revision."
            ),
        )
    project_id = str(uuid.uuid4())
    chapter_number = _chapter_number(payload.chapter_type)
    chapter_title = _chapter_title(payload.chapter_type, payload.chapter_title)
    profile = {
        "title": payload.thesis_title,
        "level": payload.academic_level,
        "programme": payload.discipline,
        "department": "",
        "institution": "",
        "research_area": payload.research_area,
        "study_context": payload.context,
        "research_approach": payload.methodology,
        "data_type": "Not specified",
        "objectives": [line.strip() for line in payload.objectives.splitlines() if line.strip()],
        "research_questions": [line.strip() for line in payload.research_questions.splitlines() if line.strip()],
        "hypotheses": [line.strip() for line in payload.hypotheses.splitlines() if line.strip()],
        "variables": {"raw_variables": [line.strip() for line in payload.variables_constructs.splitlines() if line.strip()]},
        "format_notes": payload.school_guidelines,
        "source_bank": payload.source_bank,
        "source_search_terms": payload.source_search_terms,
        "project_kind": "external_revision",
        "external_revision_chapter_number": chapter_number,
        "external_revision_chapter_type": payload.chapter_type,
        "external_revision_chapter_title": chapter_title,
        "study_stage": payload.study_stage,
        "citation_style": payload.citation_style,
        "theory_framework": payload.theory_framework,
        "contribution_claim": payload.contribution_claim,
        "data_and_results": payload.data_and_results,
        "created_for": "chapter_strengthener",
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }
    drafts = {str(chapter_number): payload.chapter_text}
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, title, profile_json, selected_sections_json, drafts_json, checks_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                payload.thesis_title,
                json.dumps(profile),
                "{}",
                json.dumps(drafts),
                "{}",
            ),
        )
        conn.commit()

    try:
        recovery = set_project_recovery(
            project_id,
            payload.recovery_email,
            payload.recovery_pin,
        )
    except ValueError as exc:
        with get_conn() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "id": project_id,
        "title": payload.thesis_title,
        "profile": profile,
        "drafts": drafts,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "purchase_mode": "revision_only",
        "recovery_enabled": recovery.get("recovery_enabled", True),
        "message": (
            "Revision-only project created. Use the revision-only checkout to unlock "
            "one strengthening revision, one compliance check and one DOCX export."
        ),
    }


@router.post("/api/projects/{project_id}/chapter-strengthener/revise")
def strengthen_project_chapter(
    project_id: str,
    payload: ChapterRevisionRequest,
    request: Request,
) -> dict[str, Any]:
    project = _project_or_404(project_id)
    if not payload.academic_integrity_confirmed or not payload.user_contribution_confirmed:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm the responsible-use and user-contribution declarations before strengthening the chapter."
            ),
        )
    chapter_number = _chapter_number(payload.chapter_type)
    title = _chapter_title(payload.chapter_type, payload.chapter_title)
    merged_payload = _merge_project_profile(payload.model_dump(), project)

    if chapter_number == 4 and not str(merged_payload.get("data_and_results") or "").strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Chapter Four strengthening requires confirmed results or findings. "
                "Paste the results or upload them in the Thesis Workspace before continuing."
            ),
        )

    try:
        with _paid_context(
            request,
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_title=title,
            action="revision",
        ):
            result = revise_chapter(merged_payload)

            if bool(merged_payload.get("save_to_project", True)):
                profile = project.get("profile") or {}
                strengthener_store = profile.get("chapter_strengthener") or {}
                strengthener_store[str(chapter_number)] = {
                    "chapter_type": payload.chapter_type,
                    "chapter_title": title,
                    "original_chapter_text": payload.chapter_text,
                    "revised_chapter_text": result.get("revised_chapter_text", ""),
                    "strengthening_report": result.get("strengthening_report", ""),
                    "supervisor_response_matrix": result.get("supervisor_response_matrix", ""),
                    "word_count": result.get("word_count", 0),
                    "estimated_pages": result.get("estimated_pages", 0),
                    "citations_per_1000_words": result.get("citations_per_1000_words", 0),
                    "source_bank_count": result.get("source_bank_count", 0),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                profile["chapter_strengthener"] = strengthener_store
                drafts = project.get("drafts") or {}
                drafts[str(chapter_number)] = result.get("revised_chapter_text", "")
                with get_conn() as conn:
                    conn.execute(
                        """
                        UPDATE projects
                        SET profile_json = ?, drafts_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (json.dumps(profile), json.dumps(drafts), project_id),
                    )
                    conn.commit()
                result["saved_to_project"] = True
                result["saved_chapter_number"] = chapter_number
            else:
                result["saved_to_project"] = False

            result["project_id"] = project_id
            result["entitlement_action"] = "revision"
            return result
    except PaymentRequiredError as exc:
        raise HTTPException(
            status_code=402,
            detail=_payment_detail(str(exc), "revision", chapter_number),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Chapter strengthening failed: {str(exc)[:240]}",
        ) from exc


@router.post("/api/projects/{project_id}/chapter-strengthener/export")
def export_project_strengthened_chapter(
    project_id: str,
    payload: ChapterRevisionExportRequest,
    request: Request,
) -> StreamingResponse:
    _project_or_404(project_id)
    chapter_number = _chapter_number(payload.chapter_type)
    title = _chapter_title(payload.chapter_type, payload.chapter_title)
    try:
        with _paid_context(
            request,
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_title=title,
            action="export",
        ):
            stream, filename = export_revised_chapter_docx(
                original_chapter_text=payload.original_chapter_text,
                revised_chapter_text=payload.revised_chapter_text,
                title=title,
                strengthening_report=payload.strengthening_report,
                supervisor_response_matrix=payload.supervisor_response_matrix,
                include_strengthening_report=payload.include_strengthening_report,
            )
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except PaymentRequiredError as exc:
        raise HTTPException(
            status_code=402,
            detail=_payment_detail(str(exc), "export", chapter_number),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Chapter export failed: {str(exc)[:240]}",
        ) from exc
