from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.database import get_conn, row_to_dict
from app.ai_service import _chapter_length_requirements
from app.chapter_revision_service import chapter_planning_targets
from app.access_control import reserve_complimentary_for_background, rollback_complimentary_usage
from app.jobs.store import (
    cancel_job,
    create_job,
    find_active_job,
    get_job,
    init_job_tables,
    verify_job_token,
)
from app.payments.entitlements import is_free_generation_allowed
from app.payments.guard import credentials_from_request, request_access_snapshot
from app.payments.internal_access import is_internal_purchase_id, validate_internal_access
from app.payments.store import claim_entitlement, rollback_claim
from app.schemas import ChapterRevisionRequest, DraftRequest
from app.template_store import get_chapter

router = APIRouter(tags=["background jobs"])
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def _enabled() -> bool:
    return str(os.getenv("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job.get("id"),
        "job_type": job.get("job_type"),
        "project_id": job.get("project_id"),
        "chapter_number": job.get("chapter_number"),
        "status": job.get("status"),
        "progress": int(job.get("progress") or 0),
        "stage": job.get("stage"),
        "message": job.get("message"),
        "error": (
            "The request could not be completed after automatic retries. Any reserved paid entitlement or complimentary page credits were returned."
            if str(job.get("status")) == "failed" else ""
        ),
        "result": job.get("result") if str(job.get("status")) == "completed" else {},
        "attempts": int(job.get("attempts") or 0),
        "max_attempts": int(job.get("max_attempts") or 0),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "completed_at": job.get("completed_at"),
    }


def _reserve_paid_action(
    *,
    request: Request,
    job_id: str,
    product_area: str,
    project_id: str,
    chapter_number: int,
    chapter_title: str,
    action: str,
    requested_pages: int = 0,
) -> dict[str, Any]:
    snapshot = request_access_snapshot(request, product_area)
    if snapshot["temporary_open"]:
        return {
            "claimed": False,
            "open_access": True,
            "access_type": "temporary_open",
            "product_area": product_area,
        }

    if snapshot["has_complimentary"]:
        try:
            return reserve_complimentary_for_background(
                raw_token=snapshot["complimentary_token"],
                supplied_email=snapshot["complimentary_email"],
                product_area=product_area,
                project_id=project_id,
                chapter_number=chapter_number,
                action=action,
                requested_pages=requested_pages,
                idempotency_key=job_id,
                metadata={"execution": "background_worker", "job_id": job_id, "module": product_area},
            )
        except PermissionError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc

    credentials = credentials_from_request(request)
    purchase_id = credentials["purchase_id"]
    access_token = credentials["access_token"]
    if not purchase_id or not access_token:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "chapter_payment_required",
                "message": "Paid chapter access is required for this background action.",
                "action": action,
                "chapter_number": chapter_number,
                "checkout_endpoint": "/api/payments/checkout",
            },
        )

    if is_internal_purchase_id(purchase_id):
        try:
            internal = validate_internal_access(
                purchase_id=purchase_id,
                access_token=access_token,
                product_area=product_area,
                project_id=project_id,
                chapter_number=chapter_number,
                action=action,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        return {
            "claimed": False,
            "internal_access": True,
            "access_type": "internal_admin",
            "purchase_id": purchase_id,
            "product_area": product_area,
            "validated": internal,
        }

    try:
        claim = claim_entitlement(
            purchase_id=purchase_id,
            access_token=access_token,
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            action=action,
            idempotency_key=job_id,
            metadata={
                "product_area": product_area,
                "module": product_area,
                "execution": "background_worker",
                "job_id": job_id,
            },
            database_url=DATABASE_URL,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    usage = claim.get("usage") or {}
    return {
        "claimed": bool(claim.get("claimed")),
        "internal_access": False,
        "usage_id": usage.get("id"),
        "purchase_id": purchase_id,
        "product_area": product_area,
    }


def _rollback_reserved_claim(claim: dict[str, Any]) -> None:
    usage_id = str(claim.get("usage_id") or "")
    if usage_id and claim.get("claimed"):
        rollback_claim(usage_id, database_url=DATABASE_URL)
    complimentary_usage_id = str(claim.get("complimentary_usage_id") or "")
    if complimentary_usage_id and claim.get("claimed"):
        rollback_complimentary_usage(complimentary_usage_id)



def _max_attempts() -> int:
    try:
        return max(1, min(int(os.getenv("PROJECTREADY_JOB_MAX_ATTEMPTS", "2") or 2), 4))
    except Exception:
        return 2


@router.post("/api/projects/{project_id}/draft-jobs", status_code=status.HTTP_202_ACCEPTED)
def queue_chapter_draft(project_id: str, payload: DraftRequest, request: Request) -> dict[str, Any]:
    if not _enabled():
        raise HTTPException(status_code=503, detail="Background processing is not enabled on this deployment.")
    init_job_tables()
    project = _project_or_404(project_id)
    try:
        chapter = get_chapter(payload.chapter_number)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    revision_mode = bool(getattr(payload, "revision_mode", False))
    action = "revision" if revision_mode else "draft"
    chapter_title = str(chapter.get("chapter_title") or f"Chapter {payload.chapter_number}")
    existing = find_active_job(
        job_type="chapter_draft",
        project_id=project_id,
        chapter_number=payload.chapter_number,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "background_job_already_active",
                "message": "A chapter request is already queued or running for this project and chapter.",
                "job_id": existing.get("id"),
            },
        )

    snapshot = request_access_snapshot(request, "thesis_workspace")
    has_protected = bool(snapshot["has_paid_or_internal"] or snapshot["has_complimentary"] or snapshot["temporary_open"])
    claim: dict[str, Any] = {}
    job_id = str(uuid.uuid4())
    planning_profile = dict(project.get("profile") or {})
    if isinstance(getattr(payload, "profile_updates", None), dict):
        planning_profile.update(payload.profile_updates or {})
    requested_pages = int(_chapter_length_requirements(planning_profile, payload.chapter_number, payload.selected_section_ids).get("maximum_pages") or 0)

    if revision_mode or has_protected:
        claim = _reserve_paid_action(
            request=request,
            job_id=job_id,
            product_area="thesis_workspace",
            project_id=project_id,
            chapter_number=payload.chapter_number,
            chapter_title=chapter_title,
            action=action,
            requested_pages=requested_pages,
        )
    else:
        if snapshot["payment_required"]:
            raise HTTPException(status_code=402, detail={
                "code": "chapter_payment_required",
                "message": "Payment is currently required for chapter generation. Use paid chapter access or a valid complimentary token.",
                "action": "draft",
                "chapter_number": payload.chapter_number,
                "checkout_endpoint": "/api/payments/checkout",
            })
        free_check = is_free_generation_allowed(
            chapter_number=payload.chapter_number,
            selected_section_ids=payload.selected_section_ids,
            revision_mode=False,
        )
        existing_free_draft = bool((project.get("drafts") or {}).get(str(payload.chapter_number), "").strip())
        if not free_check.get("allowed") or existing_free_draft:
            message = free_check.get("message") or "Unlock guided chapter development to continue."
            if existing_free_draft and free_check.get("allowed"):
                message = "The Free Starter draft for Chapter One has already been used. Unlock the chapter to generate another draft."
            raise HTTPException(status_code=402, detail={
                "code": "chapter_payment_required",
                "message": message,
                "action": "draft",
                "chapter_number": payload.chapter_number,
                "checkout_endpoint": "/api/payments/checkout",
            })

    job_payload = {
        "project_id": project_id,
        "request": payload.model_dump(mode="json"),
        "_preauthorized_claim": claim,
    }
    try:
        job, token = create_job(
            job_type="chapter_draft",
            payload=job_payload,
            project_id=project_id,
            chapter_number=payload.chapter_number,
            max_attempts=_max_attempts(),
            job_id=job_id,
            message="Chapter request queued. You may leave this page and return while the worker continues.",
        )
    except Exception:
        _rollback_reserved_claim(claim)
        raise

    return {
        "ok": True,
        "mode": "background",
        "job": _public_job(job),
        "job_token": token,
        "status_url": f"/api/jobs/{job_id}",
        "cancel_url": f"/api/jobs/{job_id}/cancel",
    }


@router.post("/api/projects/{project_id}/chapter-strengthener/jobs", status_code=status.HTTP_202_ACCEPTED)
def queue_chapter_strengthener(project_id: str, payload: ChapterRevisionRequest, request: Request) -> dict[str, Any]:
    if not _enabled():
        raise HTTPException(status_code=503, detail="Background processing is not enabled on this deployment.")
    _project_or_404(project_id)
    chapter_type = str(payload.chapter_type or "")
    chapter_number = int(chapter_type[0]) if chapter_type[:1].isdigit() else 6
    chapter_title = str(payload.chapter_title or payload.chapter_type or "Strengthened Thesis Chapter").strip()
    existing = find_active_job(
        job_type="chapter_strengthener",
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if existing:
        raise HTTPException(status_code=409, detail={
            "code": "background_job_already_active",
            "message": "A strengthening request is already queued or running for this project and chapter.",
            "job_id": existing.get("id"),
        })

    job_id = str(uuid.uuid4())
    selected_count = len(payload.selected_section_titles or []) + len(payload.new_section_titles or []) + len(payload.custom_new_sections or [])
    planning = chapter_planning_targets(
        payload.academic_level,
        payload.chapter_type,
        discipline=payload.discipline,
        strengthening_scope=payload.strengthening_scope,
        selected_section_count=selected_count,
        custom_target_pages_enabled=payload.custom_target_pages_enabled,
        target_page_min=payload.target_page_min,
        target_page_max=payload.target_page_max,
    )
    requested_pages = int((planning.get("page_range") or {}).get("maximum") or 0)
    claim = _reserve_paid_action(
        request=request,
        job_id=job_id,
        product_area="chapter_strengthener",
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        action="revision",
        requested_pages=requested_pages,
    )
    try:
        job, token = create_job(
            job_type="chapter_strengthener",
            payload={
                "project_id": project_id,
                "request": payload.model_dump(mode="json"),
                "_preauthorized_claim": claim,
            },
            project_id=project_id,
            chapter_number=chapter_number,
            max_attempts=_max_attempts(),
            job_id=job_id,
            message="Chapter strengthening queued. The selected chapter or sections will be processed in the background.",
        )
    except Exception:
        _rollback_reserved_claim(claim)
        raise
    return {
        "ok": True,
        "mode": "background",
        "job": _public_job(job),
        "job_token": token,
        "status_url": f"/api/jobs/{job_id}",
        "cancel_url": f"/api/jobs/{job_id}/cancel",
    }


@router.get("/api/jobs/{job_id}")
def job_status(job_id: str, x_projectready_job_token: str = Header(default="")) -> dict[str, Any]:
    if not verify_job_token(job_id, x_projectready_job_token):
        raise HTTPException(status_code=404, detail="Background request not found.")
    job = get_job(job_id, include_payload=False)
    if not job:
        raise HTTPException(status_code=404, detail="Background request not found.")
    return {"ok": True, "job": _public_job(job)}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_background_job(job_id: str, x_projectready_job_token: str = Header(default="")) -> dict[str, Any]:
    if not verify_job_token(job_id, x_projectready_job_token):
        raise HTTPException(status_code=404, detail="Background request not found.")
    current = get_job(job_id, include_payload=True)
    if not current:
        raise HTTPException(status_code=404, detail="Background request not found.")
    if str(current.get("status")) == "running":
        raise HTTPException(status_code=409, detail="A running request cannot be cancelled safely. It will finish or retry automatically.")
    updated = cancel_job(job_id)
    claim = (current.get("payload") or {}).get("_preauthorized_claim") or {}
    if updated and str(updated.get("status")) == "cancelled":
        _rollback_reserved_claim(claim)
    return {"ok": True, "job": _public_job(updated or current)}
