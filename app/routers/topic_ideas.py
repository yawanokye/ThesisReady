from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.topic_ideas_service import generate_topic_ideas
from app.topic_ideas_export import export_topic_ideas_docx
from app.payments.guard import PaymentRequiredError, credentials_from_request, paid_chapter_action
from app.payments.internal_access import is_internal_purchase_id, validate_internal_access
from app.payments.store import get_purchase

router = APIRouter(prefix="/api/topic-ideas", tags=["topic ideas"])
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
TOPIC_IDEAS_PLAN_KEY = "topic_ideas_access"
TOPIC_IDEAS_CHAPTER_NUMBER = 99
TOPIC_IDEAS_CHAPTER_TITLE = "Topic Ideas Access"
FREE_PREVIEW_IDEAS = 2
PAID_MAXIMUM_IDEAS = 12


class TopicIdeasRequest(BaseModel):
    research_area: str = Field(..., min_length=3)
    context: str = ""
    country_region: str = ""
    level: str = "Bachelors"
    methodology: str = "Not sure"
    data_type: str = "Not sure"
    keywords: str = ""
    trend_focus: str = ""
    max_ideas: int = Field(default=8, ge=2, le=PAID_MAXIMUM_IDEAS)
    include_older_foundational: bool = True


class TopicIdeasExportRequest(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)


def _delete_export(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


@router.post("/export-docx", response_class=FileResponse)
def export_topic_ideas(payload: TopicIdeasExportRequest, background_tasks: BackgroundTasks) -> FileResponse:
    result = payload.result or {}
    ideas = result.get("ideas") or []
    if not isinstance(ideas, list) or not ideas:
        raise HTTPException(status_code=400, detail="Generate topic ideas before exporting.")
    if len(ideas) > PAID_MAXIMUM_IDEAS:
        raise HTTPException(status_code=400, detail="A maximum of 12 topic ideas can be exported at once.")
    if len(json.dumps(result, default=str)) > 2_500_000:
        raise HTTPException(status_code=413, detail="The Topic Ideas export is too large. Generate a smaller set and try again.")

    export_dir = Path(tempfile.gettempdir()) / "projectready-topic-ideas-exports"
    path = export_topic_ideas_docx(result, export_dir)
    background_tasks.add_task(_delete_export, str(path))
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
        background=background_tasks,
    )


def _run_generation(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = generate_topic_ideas(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Topic idea generation failed: {str(exc)[:240]}",
        ) from exc
    return result


@router.post("")
def create_topic_ideas(payload: TopicIdeasRequest, request: Request) -> dict[str, Any]:
    credentials = credentials_from_request(request)
    purchase_id = credentials["purchase_id"]
    access_token = credentials["access_token"]

    # Free preview: no payment credential is required. The server, rather than
    # the browser, enforces the two-idea limit so changing the page controls
    # cannot unlock the paid result set.
    if not purchase_id and not access_token:
        free_payload = payload.model_dump()
        free_payload["max_ideas"] = FREE_PREVIEW_IDEAS
        result = _run_generation(free_payload)
        result.update(
            {
                "access_tier": "free_preview",
                "free_preview": True,
                "ideas_returned": len(result.get("ideas") or []),
                "maximum_ideas": FREE_PREVIEW_IDEAS,
                "paid_maximum_ideas": PAID_MAXIMUM_IDEAS,
                "unlock": {
                    "required": True,
                    "checkout_endpoint": "/api/topic-ideas/checkout",
                    "ghana_price": "GHS 10",
                    "international_price": "US$1.50",
                    "message": "Unlock one full generation of up to 12 ideas to compare and select from.",
                },
            }
        )
        return result

    # A partial or invalid credential should not be treated as paid access.
    if not purchase_id or not access_token:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "topic_ideas_access_credential_incomplete",
                "message": "The Topic Ideas access credential is incomplete. Generate the two free ideas or complete checkout to unlock up to 12.",
                "checkout_endpoint": "/api/topic-ideas/checkout",
            },
        )

    purchase = get_purchase(purchase_id, database_url=DATABASE_URL)
    internal_access = None
    if is_internal_purchase_id(purchase_id):
        try:
            internal_access = validate_internal_access(
                purchase_id=purchase_id,
                access_token=access_token,
                product_area="topic_ideas",
                chapter_number=TOPIC_IDEAS_CHAPTER_NUMBER,
                action="draft",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=402, detail={
                "reason": "topic_ideas_internal_access_invalid",
                "message": str(exc),
                "checkout_endpoint": "/api/topic-ideas/checkout",
            }) from exc
    elif not purchase or str(purchase.get("plan_key") or "") != TOPIC_IDEAS_PLAN_KEY:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "topic_ideas_payment_required",
                "message": "Generate two ideas free, then unlock up to 12 ideas for GHS 10 in Ghana or US$1.50 outside Ghana.",
                "checkout_endpoint": "/api/topic-ideas/checkout",
            },
        )

    paid_payload = payload.model_dump()
    paid_payload["max_ideas"] = max(
        FREE_PREVIEW_IDEAS,
        min(int(paid_payload.get("max_ideas") or PAID_MAXIMUM_IDEAS), PAID_MAXIMUM_IDEAS),
    )

    try:
        with paid_chapter_action(
            purchase_id=purchase_id,
            access_token=access_token,
            project_id=str((purchase or {}).get("project_id") or (internal_access or {}).get("project_id") or ""),
            chapter_number=TOPIC_IDEAS_CHAPTER_NUMBER,
            chapter_title=TOPIC_IDEAS_CHAPTER_TITLE,
            action="draft",
            idempotency_key=(
                str(request.headers.get("x-idempotency-key") or "").strip()
                or str(uuid.uuid4())
            ),
            metadata={
                "product_area": "topic_ideas",
                "access_tier": "paid_full_set",
                "research_area": payload.research_area[:200],
                "requested_ideas": paid_payload["max_ideas"],
            },
            database_url=DATABASE_URL,
        ):
            result = _run_generation(paid_payload)
            result.update(
                {
                    "access_tier": "internal_full_set" if internal_access else "paid_full_set",
                    "free_preview": False,
                    "ideas_returned": len(result.get("ideas") or []),
                    "maximum_ideas": PAID_MAXIMUM_IDEAS,
                    "paid_maximum_ideas": PAID_MAXIMUM_IDEAS,
                    "internal_access": bool(internal_access),
                }
            )
            return result
    except PaymentRequiredError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "topic_ideas_access_unavailable",
                "message": str(exc),
                "checkout_endpoint": "/api/topic-ideas/checkout",
            },
        ) from exc
