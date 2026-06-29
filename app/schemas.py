from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


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
    project_kind: str = "standard"
    recovery_email: str = ""
    recovery_pin: str = ""


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


# ----------------------------------------------------------------------
# Integrated Chapter Strengthener
# ----------------------------------------------------------------------

CHAPTER_STRENGTHENER_LEVELS = (
    "Bachelors",
    "Non-Research Masters",
    "Research Masters / MPhil",
    "Professional Doctorate / DBA / DEd",
    "PhD",
)

CHAPTER_STRENGTHENER_TYPES = (
    "1. Introduction",
    "2. Literature Review",
    "3. Research Methods / Methodology",
    "4. Results, Data Analysis and Discussion",
    "5. Summary, Conclusions and Recommendations",
    "Other Chapter",
)


class ChapterRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    thesis_title: str = Field(..., min_length=3)
    chapter_title: str = ""
    chapter_type: str = "1. Introduction"
    chapter_text: str = Field(..., min_length=100)
    academic_level: str = "Bachelors"
    discipline: str = ""
    study_stage: str = "Completed study"
    research_area: str = ""
    context: str = ""
    objectives: str = ""
    research_questions: str = ""
    hypotheses: str = ""
    theory_framework: str = ""
    variables_constructs: str = ""
    methodology: str = ""
    data_and_results: str = ""
    contribution_claim: str = ""
    school_guidelines: str = ""
    citation_style: str = "APA 7th"
    revision_level: str = "Comprehensive chapter strengthening"
    revision_goals: str = ""
    supervisor_comments: str = ""
    strengthen_structure: bool = True
    strengthen_problem_gap: bool = True
    strengthen_conceptualisation: bool = True
    increase_citation_density: bool = True
    assess_method_fit: bool = True
    assess_results: bool = True
    deepen_discussion: bool = True
    strengthen_conclusions: bool = True
    improve_language: bool = True
    include_supervisor_response_matrix: bool = True
    include_source_search: bool = True
    include_older_foundational: bool = True
    source_search_terms: str = ""
    source_limit: int = 45
    source_bank: list[dict[str, Any]] = Field(default_factory=list)
    save_to_project: bool = True

    @field_validator("academic_level")
    @classmethod
    def validate_strengthener_level(cls, value: str) -> str:
        aliases = {
            "Research Masters (e.g. MPhil)": "Research Masters / MPhil",
            "Professional Doctorate (e.g. DBA, DEd)": "Professional Doctorate / DBA / DEd",
            "Professional Doctorate": "Professional Doctorate / DBA / DEd",
        }
        normalised = aliases.get(value, value)
        return normalised if normalised in CHAPTER_STRENGTHENER_LEVELS else "Bachelors"

    @field_validator("chapter_type")
    @classmethod
    def validate_strengthener_chapter(cls, value: str) -> str:
        return value if value in CHAPTER_STRENGTHENER_TYPES else "Other Chapter"

    @field_validator("revision_level")
    @classmethod
    def validate_strengthener_revision_level(cls, value: str) -> str:
        allowed = {
            "Language and clarity polish",
            "Substantive scholarly strengthening",
            "Comprehensive chapter strengthening",
        }
        return value if value in allowed else "Comprehensive chapter strengthening"

    @field_validator("source_limit")
    @classmethod
    def validate_strengthener_source_limit(cls, value: int) -> int:
        return max(3, min(int(value), 60))

    @field_validator("source_bank")
    @classmethod
    def validate_strengthener_source_bank(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)][:120]


class ChapterRevisionExportRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    chapter_title: str = "Strengthened Thesis Chapter"
    chapter_type: str = "1. Introduction"
    academic_level: str = "Bachelors"
    original_chapter_text: str = Field(..., min_length=10)
    revised_chapter_text: str = Field(..., min_length=10)
    strengthening_report: str = ""
    supervisor_response_matrix: str = ""
    include_strengthening_report: bool = True


class ChapterTargetRequest(BaseModel):
    academic_level: str = "Bachelors"
    chapter_type: str = "1. Introduction"


class ProjectRecoveryRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    recovery_pin: str = Field(..., min_length=6, max_length=6)


class ProjectRecoverySetupRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    recovery_pin: str = Field(..., min_length=6, max_length=6)


class ExternalRevisionProjectCreate(ChapterRevisionRequest):
    recovery_email: str = Field(..., min_length=5, max_length=254)
    recovery_pin: str = Field(..., min_length=6, max_length=6)
