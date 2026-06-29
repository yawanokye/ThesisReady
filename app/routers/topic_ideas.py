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


class TopicIdeasRequest(BaseModel):
    research_area: str = Field(..., min_length=3)
    context: str = ""
    country_region: str = ""
    level: str = "Bachelors"
    methodology: str = "Not sure"
    data_type: str = "Not sure"
    keywords: str = ""
    trend_focus: str = ""
    max_ideas: int = 8
    include_older_foundational: bool = True


@router.post("")
def create_topic_ideas(payload: TopicIdeasRequest, request: Request) -> dict[str, Any]:
    credentials = credentials_from_headers(request.headers)
    purchase = get_purchase(credentials["purchase_id"], database_url=DATABASE_URL)
    if not purchase or str(purchase.get("plan_key") or "") != TOPIC_IDEAS_PLAN_KEY:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "topic_ideas_payment_required",
                "message": "Paid Topic Ideas access is required. Ghana access is GHS 10 and access outside Ghana is US$1.50.",
                "checkout_endpoint": "/api/topic-ideas/checkout",
            },
        )

    try:
        with paid_chapter_action(
            purchase_id=credentials["purchase_id"],
            access_token=credentials["access_token"],
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
                "research_area": payload.research_area[:200],
                "requested_ideas": payload.max_ideas,
            },
            database_url=DATABASE_URL,
        ):
            return generate_topic_ideas(payload.model_dump())
    except PaymentRequiredError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "topic_ideas_access_unavailable",
                "message": str(exc),
                "checkout_endpoint": "/api/topic-ideas/checkout",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Topic idea generation failed: {str(exc)[:240]}") from exc
