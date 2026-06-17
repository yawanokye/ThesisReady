from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.topic_ideas_service import generate_topic_ideas

router = APIRouter(prefix="/api/topic-ideas", tags=["topic ideas"])


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
def create_topic_ideas(payload: TopicIdeasRequest) -> dict[str, Any]:
    try:
        return generate_topic_ideas(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Topic idea generation failed: {str(exc)[:240]}") from exc
