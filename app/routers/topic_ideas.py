from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.topic_ideas_service import generate_topic_ideas
from app.payments.guard import PaymentRequiredError, credentials_from_headers, paid_chapter_action
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
    credentials = credentials_from_headers(request.headers)
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
    if not purchase or str(purchase.get("plan_key") or "") != TOPIC_IDEAS_PLAN_KEY:
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
            project_id=str(purchase.get("project_id") or ""),
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
                    "access_tier": "paid_full_set",
                    "free_preview": False,
                    "ideas_returned": len(result.get("ideas") or []),
                    "maximum_ideas": PAID_MAXIMUM_IDEAS,
                    "paid_maximum_ideas": PAID_MAXIMUM_IDEAS,
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
