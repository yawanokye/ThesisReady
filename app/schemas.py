from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=3)
    programme: str = ""
    department: str = ""
    institution: str = ""
    level: str = "Bachelors"
    academic_level_guidance: str = ""
    reference_currency_rule: str = ""
    research_area: str = ""
    study_context: str = ""
    research_approach: str = "Quantitative"
    data_type: str = "Primary data"
    expected_chapters: int = 5
    variables: dict[str, Any] = Field(default_factory=dict)
    objectives: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    notes: str = ""


class SectionSelection(BaseModel):
    chapter_number: int
    selected_section_ids: list[str]


class DraftRequest(BaseModel):
    chapter_number: int
    selected_section_ids: list[str]
    answers: dict[str, Any] = Field(default_factory=dict)
    extra_instructions: str = ""
    use_ai: bool = True


class DraftResponse(BaseModel):
    chapter_number: int
    chapter_title: str
    draft: str
    source: str


class ComplianceRequest(BaseModel):
    chapter_number: int
    selected_section_ids: list[str]
    draft: str | None = None


class ComplianceItem(BaseModel):
    section_id: str
    section_title: str
    requirement: str
    status: str
    evidence: str
    suggested_action: str


class ComplianceResponse(BaseModel):
    chapter_number: int
    score_percent: float
    items: list[ComplianceItem]
