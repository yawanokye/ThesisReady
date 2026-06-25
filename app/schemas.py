from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(..., min_length=3)
    programme: str = ""
    department: str = ""
    institution: str = ""
    level: str = "Bachelors"
    academic_level_guidance: str = ""
    reference_currency_rule: str = ""
    thesis_format: str = "Standard five-chapter thesis/dissertation"
    format_notes: str = ""
    research_area: str = ""
    study_context: str = ""
    citation_evidence_notes: str = ""
    research_approach: str = "Quantitative"
    data_type: str = "Primary data"
    expected_chapters: int = 5
    variables: dict[str, Any] = Field(default_factory=dict)
    objectives: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    notes: str = ""
    retrieved_sources: dict[str, Any] = Field(default_factory=dict)
    source_bank: list[dict[str, Any]] = Field(default_factory=list)
    source_search_terms: str = ""
    other_chapter_title: str = ""
    other_chapter_instructions: str = ""
    draft_maturity: str = "Supervisor-ready draft"
    student_contribution: dict[str, Any] = Field(default_factory=dict)


class SectionSelection(BaseModel):
    chapter_number: int
    selected_section_ids: list[str]


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    chapter_number: int
    selected_section_ids: list[str]
    answers: dict[str, Any] = Field(default_factory=dict)
    extra_instructions: str = ""
    use_ai: bool = True
    revision_mode: bool = False
    revision_instructions: str = ""
    revision_text: str = ""
    existing_chapter_text: str = ""
    uploaded_revision_text: str = ""
    revision_filename: str = ""
    retrieved_sources: dict[str, Any] = Field(default_factory=dict)
    source_bank: list[dict[str, Any]] = Field(default_factory=list)
    source_search_terms: str = ""
    other_chapter_title: str = ""
    other_chapter_instructions: str = ""
    draft_maturity: str = "Supervisor-ready draft"
    student_contribution: dict[str, Any] = Field(default_factory=dict)
    human_revision_pass: bool = True


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


class SourceSearchRequest(BaseModel):
    query: str = ""
    max_results: int = 30
    include_older_foundational: bool = True
    use_relevance_gate: bool = True
    attach_not_relevant_sources: bool = True
