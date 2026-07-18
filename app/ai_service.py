from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv

from app.template_store import get_chapter, selected_sections
from app.action_items import detach_action_items
from app.scholarly_humanizer import (
    analyse_scholarly_style,
    build_humanizer_batches,
    humanize_scholarly_text,
    humanizer_variation_profile,
    scholarly_humanizer_prompt_rules,
    validate_humanizer_preservation,
    variation_targets_met,
)

load_dotenv()


# ----------------------------------------------------------------------
# CHAPTER DEPTH, PAGE AND CITATION TARGETS
# ----------------------------------------------------------------------

WORDS_PER_PAGE_ESTIMATE = max(280, int(os.getenv("PROJECTREADY_WORDS_PER_PAGE", "330") or 330))

# Page ranges supplied for the standard five-chapter thesis/dissertation format.
# The targets guide generation depth. They are estimates because tables, equations,
# figures, headings and reference lists change the final DOCX pagination.
CHAPTER_PAGE_TARGETS: dict[str, dict[int, tuple[int, int]]] = {
    "bachelors": {
        1: (10, 15), 2: (15, 22), 3: (10, 15), 4: (20, 25), 5: (8, 12),
    },
    "nonresearch_masters": {
        1: (10, 15), 2: (20, 30), 3: (12, 18), 4: (20, 30), 5: (8, 15),
    },
    "research_masters": {
        1: (15, 20), 2: (35, 45), 3: (15, 22), 4: (20, 32), 5: (8, 12),
    },
    "professional_doctorate": {
        1: (15, 22), 2: (40, 60), 3: (25, 35), 4: (35, 45), 5: (10, 15),
    },
    "phd": {
        1: (25, 35), 2: (60, 80), 3: (30, 45), 4: (60, 80), 5: (20, 30),
    },
}

# Planning guides, not mechanical quotas. Citations must still pass the relevance
# and source-integrity checks before they are inserted.
CITATION_DENSITY_TARGETS: dict[str, dict[int, tuple[int, int]]] = {
    # Citation-occurrence planning ranges per 1,000 substantive words. These
    # stronger ranges apply across all academic levels, but every citation must
    # still pass the relevance and source-integrity gate.
    "bachelors": {
        1: (12, 16), 2: (16, 22), 3: (6, 9), 4: (6, 10), 5: (4, 7),
    },
    "nonresearch_masters": {
        1: (13, 18), 2: (18, 24), 3: (7, 10), 4: (7, 11), 5: (5, 8),
    },
    "research_masters": {
        1: (15, 20), 2: (20, 28), 3: (8, 12), 4: (8, 13), 5: (6, 9),
    },
    "professional_doctorate": {
        1: (16, 22), 2: (22, 30), 3: (9, 13), 4: (9, 14), 5: (7, 10),
    },
    "phd": {
        1: (18, 24), 2: (24, 32), 3: (10, 15), 4: (10, 16), 5: (8, 12),
    },
}

# These weights help the model distribute the chapter word budget sensibly.
# Only selected sections are included, and their weights are re-normalised.
SECTION_DEPTH_WEIGHTS: dict[int, dict[str, float]] = {
    1: {
        "ch1_chapter_intro": 0.03, "ch1_background": 0.28, "ch1_problem": 0.22,
        "ch1_purpose": 0.04, "ch1_objectives": 0.06, "ch1_questions": 0.06,
        "ch1_significance": 0.12, "ch1_delimitations": 0.05, "ch1_limitations": 0.05,
        "ch1_structure": 0.04,
    },
    2: {
        "ch2_intro": 0.04, "ch2_concepts": 0.12, "ch2_conceptual_review": 0.19,
        "ch2_theoretical": 0.21, "ch2_empirical_objectives": 0.34,
        "ch2_framework": 0.07, "ch2_summary": 0.03,
    },
    3: {
        "ch3_intro": 0.03, "ch3_philosophy": 0.07, "ch3_approach": 0.06,
        "ch3_design": 0.08, "ch3_population": 0.07, "ch3_sampling": 0.09,
        "ch3_data_source": 0.06, "ch3_instrument": 0.09, "ch3_measurement": 0.09,
        "ch3_validity": 0.08, "ch3_collection": 0.07, "ch3_preparation": 0.06,
        "ch3_analysis": 0.11, "ch3_ethics": 0.04, "ch3_chapter_summary": 0.02,
    },
    4: {
        "ch4_intro": 0.03, "ch4_response_rate": 0.05, "ch4_profile": 0.10,
        "ch4_descriptive": 0.10, "ch4_objective_results": 0.35,
        "ch4_discussion": 0.32, "ch4_summary": 0.05,
    },
    5: {
        "ch5_intro": 0.03, "ch5_summary_study": 0.10, "ch5_summary_findings": 0.30,
        "ch5_conclusions": 0.22, "ch5_recommendations": 0.25, "ch5_future": 0.10,
    },
}


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_plain_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_plain_text(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _length_level(profile: dict[str, Any]) -> str:
    """Normalise the selected level while preserving PhD/professional-doctorate differences."""
    raw = str(
        profile.get("level")
        or profile.get("academic_level")
        or profile.get("study_level")
        or "Bachelors"
    ).strip().lower()
    if "phd" in raw or "doctor of philosophy" in raw:
        return "phd"
    if any(token in raw for token in ["professional doctorate", "professional doctor", "dba", "ded", "d.ed"]):
        return "professional_doctorate"
    if any(token in raw for token in ["non-research", "non research", "coursework", "taught masters", "taught master's", "mba"]):
        return "nonresearch_masters"
    if any(token in raw for token in ["research masters", "research master's", "mphil", "m.phil", "master of philosophy"]):
        return "research_masters"
    if any(token in raw for token in ["msc", "m.sc", "ma", "m.a", "masters", "master's"]):
        return "nonresearch_masters"
    return "bachelors"


def _chapter_length_requirements(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return page, word, section and citation-density targets for a chapter."""
    level = _length_level(profile)
    chapter_number = int(chapter_number or 0)
    pages = CHAPTER_PAGE_TARGETS.get(level, {}).get(chapter_number)
    if not pages:
        # Custom chapters and the supplementary guide remain scope-led.
        pages = (8, 18) if chapter_number == 7 else (8, 20)

    custom_targets = profile.get("custom_page_targets") or {}
    current_custom = profile.get("current_custom_page_target") or {}
    custom_range: dict[str, Any] | None = None
    if isinstance(custom_targets, dict):
        raw_custom = custom_targets.get(str(chapter_number))
        if isinstance(raw_custom, dict):
            custom_range = raw_custom
    if not custom_range and isinstance(current_custom, dict):
        try:
            if int(current_custom.get("chapter") or 0) == chapter_number and str(current_custom.get("mode") or "") == "custom":
                custom_range = current_custom
        except Exception:
            custom_range = None
    if isinstance(custom_range, dict):
        try:
            cmin = int(float(custom_range.get("minimum") or custom_range.get("min") or 0))
            cmax = int(float(custom_range.get("maximum") or custom_range.get("max") or 0))
            if cmin > 0 and cmax >= cmin and cmax <= 180:
                pages = (cmin, cmax)
        except Exception:
            pass

    min_pages, max_pages = pages
    min_words = min_pages * WORDS_PER_PAGE_ESTIMATE
    max_words = max_pages * WORDS_PER_PAGE_ESTIMATE
    target_words = int(round(((min_words + max_words) / 2) / 100.0) * 100)

    citation_range = CITATION_DENSITY_TARGETS.get(level, {}).get(chapter_number, (3, 6))
    selected_section_ids = [str(x) for x in (selected_section_ids or []) if str(x).strip()]
    weights = SECTION_DEPTH_WEIGHTS.get(chapter_number, {})
    selected_weights = {sid: float(weights.get(sid, 1.0)) for sid in selected_section_ids}
    weight_total = sum(selected_weights.values()) or max(1, len(selected_section_ids))
    section_word_budgets = {
        sid: {
            "target_words": max(180, int(round((target_words * weight / weight_total) / 50.0) * 50)),
            "minimum_words": max(120, int(round((min_words * weight / weight_total) / 50.0) * 50)),
        }
        for sid, weight in selected_weights.items()
    }

    requirements = {
        "length_level": level,
        "target_page_range": f"{min_pages}-{max_pages}",
        "minimum_pages": min_pages,
        "maximum_pages": max_pages,
        "words_per_page_estimate": WORDS_PER_PAGE_ESTIMATE,
        "minimum_words": min_words,
        "target_words": target_words,
        "maximum_words": max_words,
        "citation_occurrences_per_1000_words": {
            "minimum": citation_range[0],
            "target": citation_range[1],
        },
        "estimated_minimum_citation_occurrences": int(round(min_words * citation_range[0] / 1000)),
        "estimated_target_citation_occurrences": int(round(target_words * citation_range[1] / 1000)),
        "section_word_budgets": section_word_budgets,
        "important_length_rules": [
            "Treat the page range as a depth target, not permission to add filler or repeat ideas.",
            "Develop each selected section to its allocated word budget using evidence, comparison, critique, interpretation and study-specific relevance.",
            "Tables, equations, figures, headings and references affect final pagination, so word counts are planning estimates rather than exact page guarantees.",
            "Where evidence is insufficient, use a precise bracketed attention placeholder instead of inventing facts or padding the chapter with generic prose.",
            "Do not compress a doctoral chapter into a short overview. Do not inflate a lower-level chapter with doctoral complexity that is not required.",
            "When a chapter is very long, develop it as linked section batches and then merge for coherence instead of compressing the whole chapter into one shallow pass.",
        ],
        "citation_density_rules": [
            "Use the citation-density range as a planning guide, never as a mechanical quota.",
            "Every citation must directly support the sentence or paragraph in which it appears.",
            "Distribute citations across substantive paragraphs instead of placing a citation cluster only at the end of a section.",
            "In Chapter One, most substantive background and problem paragraphs should contain at least one directly relevant citation, and evidence-heavy paragraphs may synthesise two or more sources.",
            "In Chapter Two, nearly every substantive paragraph should be evidence-supported and thematic synthesis should normally compare two to four relevant sources rather than rely on one citation repeatedly.",
            "Chapter Two should compare multiple studies within thematic and objective-led synthesis, not present one study per paragraph as an annotated list.",
            "Chapter Four should keep results reporting evidence-based and citation-light, while the discussion should be citation-rich and connect findings to theory and prior studies.",
            "Use a bracketed source placeholder when the evidence bank is insufficient. Never fabricate a source to meet the density target.",
        ],
    }
    requirements["long_chapter_strategy"] = _long_chapter_strategy(profile, chapter_number, selected_section_ids, requirements)
    return requirements


def _chapter_word_count(text: str) -> int:
    """Estimate substantive chapter words, excluding references and audit material."""
    cleaned = text or ""
    reference_heading = re.search(r"(?im)^#{0,4}\s*references\s*$", cleaned)
    if reference_heading:
        cleaned = cleaned[: reference_heading.start()]
    audit_heading = re.search(r"(?im)^#{0,4}\s*source\s+use\s+audit\b", cleaned)
    if audit_heading:
        cleaned = cleaned[: audit_heading.start()]
    cleaned = re.sub(r"```.*?```", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"[#|*_`$<>]", " ", cleaned)
    return len(re.findall(r"\b[\w’'-]+\b", cleaned))


def _has_meaningful_user_inputs(profile: dict[str, Any], answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assess whether the user supplied enough material for a grounded draft.

    The result does not block drafting. It tells the model when to write a
    provisional working draft and where to insert attention placeholders.
    """
    answers = answers or {}
    flat_answers = _plain_text(answers)
    contribution = profile.get("student_contribution") or {}
    profile_values = [
        profile.get("research_area", ""),
        profile.get("study_context", ""),
        profile.get("citation_evidence_notes", ""),
        profile.get("format_notes", ""),
        profile.get("objectives", []),
        profile.get("research_questions", []),
        profile.get("hypotheses", []),
        profile.get("variables", {}),
        contribution.get("central_argument", "") if isinstance(contribution, dict) else "",
        contribution.get("local_context_notes", "") if isinstance(contribution, dict) else "",
        contribution.get("evidence_anchors", "") if isinstance(contribution, dict) else "",
        contribution.get("supervisor_comments", "") if isinstance(contribution, dict) else "",
        flat_answers,
    ]
    total_chars = len(_plain_text(profile_values))
    supplied = {
        "research_area": bool(str(profile.get("research_area") or "").strip()),
        "study_context": len(str(profile.get("study_context") or "").strip()) >= 30,
        "objectives": bool(profile.get("objectives")),
        "evidence_notes": len(str(profile.get("citation_evidence_notes") or "").strip()) >= 40,
        "guided_answers": len(flat_answers) >= 80,
    }
    missing = []
    if not supplied["research_area"]:
        missing.append("research area")
    if not supplied["study_context"]:
        missing.append("study context")
    if not supplied["objectives"] and not supplied["guided_answers"]:
        missing.append("objectives, questions or section answers")
    if not supplied["evidence_notes"]:
        missing.append("verified evidence, statistics or source notes")
    mode = "grounded_draft" if total_chars >= 450 and sum(supplied.values()) >= 3 else "provisional_draft_for_user_consideration"
    return {
        "mode": mode,
        "input_character_count": total_chars,
        "supplied_signals": supplied,
        "missing_inputs": missing,
        "rules": [
            "Encourage the student to provide topic-specific information, but do not refuse to prepare a working draft when information is limited.",
            "When information is limited, prepare a provisional draft for the user's consideration using the available title, level, broad topic and chapter requirements.",
            "Do not claim that the provisional text is final, verified or submission-ready.",
            "Use bracketed attention placeholders for missing facts, context, data, citations, objective wording, theory decisions, methods and institutional details.",
            "Avoid fabricating references, statistics, sample sizes, results, ethical approvals or school requirements.",
            "Make the draft useful enough for the user to edit, confirm, reject, replace or enrich with their own information.",
        ],
    }


def _long_chapter_strategy(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    length_requirements: dict[str, Any],
) -> dict[str, Any]:
    """Describe how the app should handle very long chapters.

    This is especially important for doctoral literature reviews, where one
    whole-chapter generation pass tends to produce shallow coverage.
    """
    target_words = int(length_requirements.get("target_words") or 0)
    level = str(length_requirements.get("length_level") or _length_level(profile))
    chapter_number = int(chapter_number or 0)
    long_threshold = int(os.getenv("PROJECTREADY_LONG_CHAPTER_THRESHOLD_WORDS", "12000") or 12000)
    doctoral = level in {"phd", "professional_doctorate"}
    is_literature = chapter_number == 2
    if target_words < long_threshold and not (doctoral and is_literature):
        return {"enabled": False, "mode": "standard_chapter_generation"}

    units: list[dict[str, Any]] = []
    if is_literature:
        units = [
            {"unit": "chapter_map", "purpose": "Build the Chapter Two argument map from Chapter One, objectives, constructs and study context before drafting."},
            {"unit": "concept_definition_bank", "purpose": "Define and distinguish the major constructs, concepts, dimensions and operational meanings."},
            {"unit": "conceptual_review", "purpose": "Develop construct-by-construct conceptual debates, mechanisms, relationships and contextual relevance."},
            {"unit": "theory_review", "purpose": "Explain, compare and justify the selected theories, including limitations and fit to the current study."},
            {"unit": "empirical_review_by_objective", "purpose": "Review empirical studies in objective-led clusters rather than a one-study-per-paragraph listing."},
            {"unit": "methodological_review", "purpose": "Synthesize methods, samples, measures, contexts and analytical techniques used in prior studies."},
            {"unit": "contextual_review", "purpose": "Compare Ghanaian, African, developing-economy and wider international evidence where relevant."},
            {"unit": "contradictions_and_debates", "purpose": "Identify inconsistent findings, theoretical disagreements, measurement problems and unresolved debates."},
            {"unit": "gap_development", "purpose": "Translate reviewed evidence into conceptual, empirical, theoretical, contextual and methodological gaps."},
            {"unit": "conceptual_framework", "purpose": "Derive the framework from the review, objectives, theories and expected relationships."},
            {"unit": "coherence_pass", "purpose": "Merge units into one chapter, remove repetition, harmonise citations and ensure cross-chapter alignment."},
        ]
    else:
        units = [
            {"unit": "chapter_map", "purpose": "Confirm section order, evidence needs and alignment with previous chapters before writing."},
            {"unit": "section_batching", "purpose": "Develop the chapter section by section or in small contiguous groups."},
            {"unit": "evidence_and_placeholder_pass", "purpose": "Use supplied evidence where available and mark missing facts or data with bracketed placeholders."},
            {"unit": "coherence_pass", "purpose": "Merge generated sections into a coherent chapter without compressing the depth."},
        ]

    max_unit_words = int(os.getenv("PROJECTREADY_LONG_CHAPTER_UNIT_TARGET_WORDS", "2500") or 2500)
    suggested_units = max(2, min(18, (max(1, target_words) + max_unit_words - 1) // max_unit_words))
    return {
        "enabled": True,
        "mode": "long_chapter_staged_development",
        "reason": "Very long chapters should be developed in smaller evidence-led units rather than one compressed pass.",
        "target_words": target_words,
        "suggested_development_units": suggested_units,
        "unit_target_words": max_unit_words,
        "recommended_workflow": units,
        "rules": [
            "Prepare a chapter map before drafting long chapters.",
            "Generate long chapters in smaller units of about 1,500 to 2,500 words where possible.",
            "For doctoral literature reviews, develop conceptual, theoretical, empirical, methodological, contextual and gap sections separately.",
            "After all units are drafted, run a coherence pass that connects arguments and removes repetition without shortening the chapter.",
            "Where student information or source evidence is missing, keep the section useful but insert bracketed attention placeholders instead of inventing material.",
        ],
    }


def _max_output_tokens_for_length(length_requirements: dict[str, Any], *, revision: bool = False) -> int:
    """Choose a bounded Responses API output limit from the requested chapter depth."""
    target_words = int(length_requirements.get("target_words") or 4000)
    # Visible English prose often needs about 1.3-1.6 tokens per word. Reasoning
    # tokens are included in max_output_tokens, so retain additional headroom.
    estimated = int(target_words * (2.0 if revision else 1.8))
    configured_cap = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "32000") or 32000)
    hard_cap = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS_HARD_CAP", "64000") or 64000)
    return max(4000, min(estimated, configured_cap, hard_cap))


def _safe_get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _reference_currency_requirements() -> dict[str, Any]:
    """Return the reference currency rule used across generated chapters."""
    current_year = datetime.now().year
    start_year = current_year - 5
    return {
        "current_year": current_year,
        "recent_reference_window": f"{start_year}-{current_year}",
        "rule": (
            f"Aim for at least 70% of substantive references to be from {start_year}-{current_year}. "
            "Where current references do not exist for a specific concept, method, context, or theory, use the strongest credible available sources. "
            "Older sources are acceptable for foundational theories, classic models, scarce-literature areas, and essential earlier studies."
        ),
        "integrity_guard": (
            "Do not fabricate citations or reference-list entries. Use sources supplied by the student or sources that can be stated with confidence. "
            "If no credible source details are available, insert a clear bracketed placeholder such as "
            f"[insert verified recent source if available, {start_year}-{current_year}] or [insert credible available source]."
        ),
    }


def _institutional_format_requirements(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    """Resolve school-format controls without forcing one universal Chapter One style."""
    format_notes = str(profile.get("format_notes") or "").strip()
    notes_lower = format_notes.lower()

    background_structure = str(profile.get("background_structure") or "continuous_narrative").strip().lower()
    if any(term in notes_lower for term in ("without subheading", "no subheading", "continuous background", "en bloc", "single block")):
        background_structure = "continuous_narrative"
    elif any(term in notes_lower for term in ("background subheading", "background subsection", "thematic background")):
        background_structure = "thematic_subsections"
    if background_structure not in {"continuous_narrative", "thematic_subsections", "follow_school_guideline"}:
        background_structure = "continuous_narrative"

    purpose_style = str(profile.get("purpose_statement_style") or "concise_general_objective").strip().lower()
    if any(term in notes_lower for term in ("purpose same as general objective", "short purpose", "concise purpose")):
        purpose_style = "concise_general_objective"
    elif any(term in notes_lower for term in ("expanded purpose", "purpose rationale")):
        purpose_style = "expanded_rationale"
    if purpose_style not in {"concise_general_objective", "concise_paragraph", "expanded_rationale"}:
        purpose_style = "concise_general_objective"

    expected_chapters = int(profile.get("expected_chapters") or 5)
    expected_chapters = max(3, min(9, expected_chapters))
    return {
        "chapter_number": int(chapter_number or 0),
        "background_structure": background_structure,
        "purpose_statement_style": purpose_style,
        "expected_chapters": expected_chapters,
        "rules": [
            "Use the project profile, title, objectives, selected method and available evidence to complete every element that can be responsibly derived.",
            "Create an ACTION REQUIRED item only for a material fact or institutional decision that cannot be inferred, retrieved or drafted safely.",
            "Do not ask the user to confirm wording merely because it was generated. Draft a defensible version for consideration.",
            "Do not repeat the same missing population, location, study-period, instrument or chapter-structure action in several sections. State it once at the first relevant point.",
            "Never leave broken phrases such as 'among in, Ghana'. Rewrite the sentence generically and add one precise action only if the missing detail is essential.",
            f"Use the configured {expected_chapters}-chapter structure when writing Organisation of the Study; do not ask whether the work has five or seven chapters when this value is available.",
        ],
        "background_rules": (
            [
                "Write Background to the Study as one continuous, coherent section under its main heading.",
                "Do not create numbered or titled subdimensions inside the background.",
                "Move from broad context to the exact study setting through paragraph transitions rather than subheadings.",
            ]
            if background_structure == "continuous_narrative"
            else [
                "Thematic lower-level subheadings may be used inside Background to the Study when they improve clarity and match the school format.",
                "Keep the sequence coherent from broad context to the exact study setting.",
            ]
        ),
        "purpose_rules": (
            [
                "Write Purpose of the Study as one concise sentence closely aligned with the general objective.",
                "A second short sentence may clarify the population or context only when that information is available.",
                "Do not add a literature review, justification, citation cluster or extended rationale under the purpose heading.",
            ]
            if purpose_style == "concise_general_objective"
            else (
                [
                    "Write Purpose of the Study as one concise paragraph of about two to four sentences.",
                    "State the overall intent first, then briefly clarify scope without repeating the problem statement.",
                ]
                if purpose_style == "concise_paragraph"
                else [
                    "Write Purpose of the Study as a developed paragraph that states the overall intent and briefly explains how it follows from the problem.",
                    "Keep it focused and avoid turning it into another background or problem section.",
                ]
            )
        ),
    }


def _citation_and_evidence_requirements(chapter_number: int) -> dict[str, Any]:
    """Return rules for evidence-led writing, citation accuracy, and problem-statement statistics."""
    current_year = datetime.now().year
    start_year = current_year - 5
    common_rules = [
        "Include relevant and accurate in-text citations in every substantive section of the write-up.",
        "Use author-year citation style unless the user or institution requests another style.",
        "Do not cite a source unless the source was supplied by the student, included in the profile/reference notes, present in uploaded material, or can be stated confidently without guessing.",
        "Where a citation is needed but no reliable source details are available, insert a bracketed attention placeholder in the draft, such as [insert verified source for this claim] rather than inventing a citation.",
        "Support factual claims with evidence. Use statistics, policy evidence, institutional records, peer-reviewed studies, official reports, or credible datasets where available.",
        f"Prioritise recent references from {start_year}-{current_year}, but use older sources when they are foundational theories, classic models, or the best credible evidence available.",
        "Do not create a reference list entry for any source unless enough accurate bibliographic information is supplied or known with confidence.",
    ]
    if chapter_number == 1:
        common_rules.extend([
            "The Background and Statement of the Problem must be evidence-led. They should include relevant factual evidence and accurate statistics where available.",
            "The Statement of the Problem must not rely on unsupported claims. It should identify the problem, provide evidence that the problem exists, show who or what is affected, and state the research gap.",
            "Use current and context-relevant statistics from credible sources such as official reports, national statistics, industry reports, policy documents, or peer-reviewed studies where supplied or confidently known.",
            "Where exact statistics are not supplied, do not invent figures. Use placeholders such as [insert current statistic from Ghana Statistical Service, World Bank, ministry report, institutional records, or peer-reviewed study] and keep the argument coherent.",
        ])
    if chapter_number == 2:
        common_rules.extend([
            "The literature review must cite studies accurately when discussing theories, concepts, empirical findings, contradictions, and gaps.",
            "Every empirical-study paragraph should identify the author/year, context, method, key finding, and relevance to the current study where available.",
        ])
    if chapter_number == 4:
        common_rules.extend([
            "Do not invent results or statistics. Interpret only the uploaded or supplied results.",
            "In the discussion, cite relevant theory and prior studies when explaining whether the findings agree, contradict, or extend existing evidence.",
        ])
    return {
        "citation_style": "Author-year in-text citations by default, unless another style is supplied.",
        "recent_reference_window": f"{start_year}-{current_year}",
        "rules": common_rules,
    }


def _level_depth_requirements(profile: dict[str, Any]) -> dict[str, str]:
    """Return writing-depth guidance based on the selected thesis/dissertation/project level."""
    level = (profile.get("level") or "Bachelors").strip()
    guidance_map = {
        "Bachelors": (
            "Write as an expert undergraduate student. Use clear definitions, relevant context, logical explanation, basic critical discussion, "
            "and a defensible but not overly complex methodology."
        ),
        "Non-Research Masters": (
            "Write as an expert non-research master's student. Emphasise professional application, practical relevance, clear synthesis, "
            "methodological clarity, and implications for practice or institutions."
        ),
        "Research Masters (e.g. MPhil)": (
            "Write as an expert research master's student. Provide deeper critical synthesis, objective-driven literature review, explicit gaps, "
            "theory-method alignment, and rigorous methodological justification."
        ),
        "Professional Doctorate (e.g. DBA, DEd)": (
            "Write as an expert professional doctorate student. Frame the work around a significant professional or organisational problem, "
            "show advanced applied scholarship, demonstrate practice-based contribution, and defend methodological choices strongly."
        ),
        "PhD": (
            "Write as an expert doctoral student. Provide publication-quality academic argument, deep theoretical engagement, advanced critical synthesis, "
            "clear originality, rigorous methodology, and a defensible contribution to knowledge."
        ),
    }
    guidance = profile.get("academic_level_guidance") or guidance_map.get(level, guidance_map["Bachelors"])
    return {"selected_level": level, "depth_guidance": guidance}


# ----------------------------------------------------------------------
# LEVEL-BASED MODEL ROUTING
# ----------------------------------------------------------------------

def _normalise_academic_level(profile: dict[str, Any]) -> str:
    """Normalise the user's selected level into a routing category."""
    raw = str(
        profile.get("level")
        or profile.get("academic_level")
        or profile.get("study_level")
        or "Bachelors"
    ).strip().lower()

    if any(token in raw for token in ["phd", "doctoral", "doctorate", "dba", "ded", "d.ed", "professional doctor"]):
        return "doctoral"
    if any(token in raw for token in ["non-research", "non research", "coursework", "taught masters", "taught master's", "mba"]):
        return "nonresearch_masters"
    if any(token in raw for token in ["research masters", "research master's", "mphil", "m.phil", "master of philosophy"]):
        return "research_masters"
    if any(token in raw for token in ["msc", "m.sc", "ma", "m.a", "masters", "master's"]):
        return "nonresearch_masters"
    return "bachelors"


def _is_core_research_chapter(chapter_number: int) -> bool:
    """Return True for chapters where prose quality and reasoning depth matter most."""
    return int(chapter_number or 0) in {1, 2, 3, 4, 5}


def _level_quality_profile(profile: dict[str, Any], chapter_number: int) -> dict[str, str]:
    """Return level-specific drafting quality expectations for prompts and routing."""
    level = _normalise_academic_level(profile)
    quality = {
        "bachelors": {
            "quality_band": "paid_bachelor_draft",
            "draft_expectation": (
                "Produce a substantial, editable thesis-standard undergraduate working draft. It must be clear, well-structured, "
                "evidence-led and academically credible, but it should not overcomplicate the theory or methodology."
            ),
        },
        "nonresearch_masters": {
            "quality_band": "paid_nonresearch_masters_draft",
            "draft_expectation": (
                "Produce a substantial, editable master's-level professional or applied working draft. It must show synthesis, practical relevance, "
                "methodological clarity and implications for practice or institutions."
            ),
        },
        "research_masters": {
            "quality_band": "paid_research_masters_draft",
            "draft_expectation": (
                "Produce a substantial, editable research-master's/MPhil working draft with deeper theoretical engagement, critical synthesis, "
                "explicit gaps, strong methodology justification and clear objective-method alignment."
            ),
        },
        "doctoral": {
            "quality_band": "paid_doctoral_draft",
            "draft_expectation": (
                "Produce a substantial, editable doctoral working draft. It should read as advanced academic prose suitable for supervisor review with originality, "
                "conceptual depth, methodological defensibility, careful critique and a clear contribution to knowledge or practice."
            ),
        },
    }[level]
    quality["normalised_level"] = level
    quality["core_research_chapter"] = "yes" if _is_core_research_chapter(chapter_number) else "no"
    return quality


def _select_draft_model(profile: dict[str, Any], chapter_number: int) -> tuple[str, str]:
    """Select the main writing model according to academic level.

    Default principle:
    - support work can use cheaper models elsewhere;
    - paid chapter drafting should use a strong writing model;
    - GPT-5.6 Terra handles most paid drafting because it balances quality and cost;
    - GPT-5.6 Sol is reserved for doctoral drafting and selective high-complexity review;
    - GPT-5.6 Luna is used only for low-cost support and fallback tasks when configured.
    """
    routing = os.getenv("PROJECTREADY_MODEL_ROUTING", "level_based").strip().lower()
    if routing in {"manual", "off", "legacy"}:
        return os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip(), "manual"

    level = _normalise_academic_level(profile)
    chapter_number = int(chapter_number or 0)

    # Optional override for the practical supplementary guide.
    if chapter_number == 7 and os.getenv("OPENAI_SUPPLEMENTARY_GUIDE_MODEL", "").strip():
        return os.getenv("OPENAI_SUPPLEMENTARY_GUIDE_MODEL", "").strip(), f"{level}:supplementary_guide"

    if level == "doctoral":
        return os.getenv("OPENAI_DOCTORAL_DRAFT_MODEL", "gpt-5.6-sol").strip(), "doctoral"

    if level == "research_masters":
        return os.getenv("OPENAI_RESEARCH_MASTERS_DRAFT_MODEL", "gpt-5.6-terra").strip(), "research_masters"

    if level == "nonresearch_masters":
        # Allow users to uplift Chapter 2/3/4 for non-research masters without changing the whole plan.
        if _is_core_research_chapter(chapter_number) and os.getenv("OPENAI_NONRESEARCH_MASTERS_CORE_MODEL", "").strip():
            return os.getenv("OPENAI_NONRESEARCH_MASTERS_CORE_MODEL", "").strip(), "nonresearch_masters:core"
        return os.getenv("OPENAI_NONRESEARCH_MASTERS_DRAFT_MODEL", "gpt-5.6-terra").strip(), "nonresearch_masters"

    # Bachelor should still be a good paid draft, not a low-tier model.
    if _is_core_research_chapter(chapter_number) and os.getenv("OPENAI_BACHELOR_CORE_MODEL", "").strip():
        return os.getenv("OPENAI_BACHELOR_CORE_MODEL", "").strip(), "bachelors:core"
    return os.getenv("OPENAI_BACHELOR_DRAFT_MODEL", "gpt-5.6-terra").strip(), "bachelors"


def _select_revision_model(profile: dict[str, Any], chapter_number: int, draft_model: str) -> str:
    """Select the model for the conservative academic revision pass."""
    routing = os.getenv("PROJECTREADY_REVISION_ROUTING", "same_as_draft").strip().lower()
    if routing in {"same", "same_as_draft", "draft"}:
        return draft_model
    if routing in {"level_based", "level"}:
        return _select_draft_model(profile, chapter_number)[0]
    if routing in {"premium", "sol", "gpt56-sol", "gpt-5.6-sol"}:
        return os.getenv("OPENAI_REVIEW_MODEL", "gpt-5.6-sol").strip()
    return os.getenv("OPENAI_REVISION_MODEL", draft_model).strip()


def _model_route_for_prompt(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    """Return a compact prompt-visible summary of the quality route, without exposing internal pricing."""
    draft_model, route = _select_draft_model(profile, chapter_number)
    qp = _level_quality_profile(profile, chapter_number)
    return {
        "routing_mode": os.getenv("PROJECTREADY_MODEL_ROUTING", "level_based"),
        "route": route,
        "draft_model_family": draft_model,
        "support_model_role": "Use lower-cost/support models only for source preparation, retraction screening, formatting, table cleanup and DOCX readiness, not for the main paid draft.",
        "quality_band": qp["quality_band"],
        "draft_expectation": qp["draft_expectation"],
    }


def _uploaded_results_for_chapter(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    uploaded = profile.get("uploaded_results") or {}
    result = uploaded.get(str(chapter_number))
    if chapter_number == 4 and not result:
        result = uploaded.get("4")
    return result or {}


def _normalise_author_for_citation(author: str) -> str:
    author = str(author or "").strip()
    if not author:
        return "[Author]"
    parts = author.replace(",", " ").split()
    return parts[-1] if parts else author


def _citation_label_for_source(src: dict[str, Any]) -> str:
    authors = src.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    year = str(src.get("year") or "n.d.").strip() or "n.d."
    cleaned = [_normalise_author_for_citation(a) for a in authors if str(a).strip()]
    if not cleaned:
        return f"([Author], {year})"
    if len(cleaned) == 1:
        return f"({cleaned[0]}, {year})"
    if len(cleaned) == 2:
        return f"({cleaned[0]} & {cleaned[1]}, {year})"
    return f"({cleaned[0]} et al., {year})"


def _source_key(src: dict[str, Any]) -> str:
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:100]
    return "title:" + title


def _merged_source_bank(profile: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
    """Merge latest retrieved sources and accumulated source bank without replacing user evidence."""
    collected: list[dict[str, Any]] = []
    for container_key in ["source_bank", "attached_sources"]:
        value = profile.get(container_key) or []
        if isinstance(value, list):
            collected.extend([v for v in value if isinstance(v, dict)])

    retrieved = profile.get("retrieved_sources") or {}
    value = retrieved.get("sources") or []
    if isinstance(value, list):
        collected.extend([v for v in value if isinstance(v, dict)])

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for idx, src in enumerate(collected, start=1):
        key = _source_key(src)
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(src)
        item["citation_key"] = f"SRC{len(merged) + 1}"
        item["in_text_citation"] = _citation_label_for_source(item)
        if not item.get("apa_hint"):
            title = item.get("title", "[Title]")
            authors = item.get("authors") or ["[Author]"]
            if isinstance(authors, str):
                authors = [authors]
            year = item.get("year") or "n.d."
            source = item.get("source") or ""
            doi = item.get("doi") or ""
            doi_text = f" https://doi.org/{doi}" if doi else ""
            item["apa_hint"] = f"{', '.join(map(str, authors))} ({year}). {title}. {source}.{doi_text}".strip()
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _source_attention_target(profile: dict[str, Any], chapter_number: int, source_count: int) -> int:
    """Suggest a defensible number of distinct source records to review for the chapter."""
    if source_count <= 0:
        return 0
    level = _length_level(profile)
    targets = {
        "bachelors": {1: 12, 2: 25, 3: 10, 4: 12, 5: 8},
        "nonresearch_masters": {1: 15, 2: 35, 3: 14, 4: 16, 5: 10},
        "research_masters": {1: 20, 2: 50, 3: 18, 4: 22, 5: 12},
        "professional_doctorate": {1: 24, 2: 60, 3: 24, 4: 28, 5: 16},
        "phd": {1: 30, 2: 75, 3: 30, 4: 40, 5: 22},
    }
    target = targets.get(level, {}).get(int(chapter_number or 0), 10)
    return min(source_count, target)


def _relevance_tier_rank(tier: Any) -> int:
    return {"highly_relevant": 3, "partly_relevant": 2, "not_relevant": 1}.get(str(tier or ""), 0)


def _source_relevance_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"highly_relevant": 0, "partly_relevant": 0, "not_relevant": 0, "unclassified": 0}
    for src in sources:
        tier = str(src.get("relevance_tier") or "unclassified")
        counts[tier] = counts.get(tier, 0) + 1
    return counts




def _previous_chapters_for_alignment(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    """Return compact previous-chapter context for cross-chapter alignment."""
    context = profile.get("previous_chapters_context") or {}
    if not isinstance(context, dict) or not context.get("available") or int(chapter_number or 0) <= 1:
        return {
            "available": False,
            "note": "No previous-chapter alignment context was supplied for this chapter.",
            "items": [],
        }
    items = []
    total = 0
    for item in context.get("items") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if len(text) < 80:
            continue
        remaining = max(0, 52000 - total)
        if remaining <= 0:
            break
        clipped = text[:remaining]
        total += len(clipped)
        items.append({
            "source": str(item.get("source") or "previous_chapter"),
            "label": str(item.get("label") or "Previous chapter context"),
            "characters": len(clipped),
            "text": clipped,
        })
    return {
        "available": bool(items),
        "target_chapter_number": int(chapter_number or 0),
        "items": items,
        "rules": context.get("rules") or [
            "Use previous chapters only for cross-chapter alignment checks.",
            "Preserve consistency with approved objectives, questions, hypotheses, variables, theory, methodology, terminology and scope.",
            "Do not copy large passages from previous chapters into the active chapter.",
            "Mark conflicts or missing alignment information with bracketed attention placeholders instead of guessing.",
        ],
    }


def _retrieved_sources_for_prompt(profile: dict[str, Any], chapter_number: int | None = None) -> dict[str, Any]:
    """Return source-search results in a compact prompt-friendly form."""
    retrieved = profile.get("retrieved_sources") or {}
    source_bank = _merged_source_bank(profile)
    compact_sources = []
    for src in source_bank:
        compact_sources.append({
            "citation_key": src.get("citation_key", ""),
            "title": src.get("title", ""),
            "authors": src.get("authors", []),
            "year": src.get("year", ""),
            "source": src.get("source", ""),
            "doi": src.get("doi", ""),
            "url": src.get("url", ""),
            "abstract": src.get("abstract", ""),
            "database": src.get("database", ""),
            "relevance_tier": src.get("relevance_tier", "unclassified"),
            "relevance_reason": src.get("relevance_reason", "No relevance explanation supplied."),
            "suggested_use": src.get("suggested_use", "Use only where it directly supports the claim."),
            "in_text_citation": src.get("in_text_citation", ""),
            "reference_entry_hint": src.get("apa_hint", ""),
        })
    compact_sources.sort(
        key=lambda item: (
            _relevance_tier_rank(item.get("relevance_tier")),
            bool(item.get("abstract")),
            bool(item.get("doi")),
        ),
        reverse=True,
    )
    total_source_count = len(compact_sources)
    target = _source_attention_target(profile, int(chapter_number or 0), total_source_count)
    prompt_source_limit = min(total_source_count, max(target, 20 if total_source_count else 0))
    compact_sources = compact_sources[:prompt_source_limit]
    return {
        "query": retrieved.get("query", ""),
        "searched_at": retrieved.get("searched_at", ""),
        "recent_reference_window": retrieved.get("recent_reference_window", ""),
        "databases": retrieved.get("databases", []),
        "usage_note": retrieved.get("usage_note", ""),
        "source_count": total_source_count,
        "sources_in_prompt": len(compact_sources),
        "relevance_counts": _source_relevance_counts(compact_sources),
        "recommended_relevant_sources_to_review": target,
        "sources": compact_sources,
        "source_use_rules": [
            "Use retrieved_sources as an additional evidence bank alongside the student's project profile, pasted verified evidence, uploaded files, and placeholders.",
            "Do not replace student-supplied evidence with search results; enrich the existing argument only where a retrieved source is directly relevant.",
            f"Use the recommended_relevant_sources_to_review value ({target}) only as a review guide, not as a compulsory citation quota.",
            "Prioritise sources marked highly_relevant, then partly_relevant. Use not_relevant sources only if a human has confirmed their relevance in the project notes.",
            "Apply a relevance gate before every citation: cite a retrieved source only when its title, abstract, method, context, theory, or finding directly supports the sentence or paragraph being written.",
            "Do not cite irrelevant, weakly related, or merely keyword-matching sources. It is better to use a placeholder than to cite an unsuitable source.",
            "Do not list retrieved sources in the References section unless they were actually cited in the chapter body.",
            "Use the supplied in_text_citation value for author-year citations where possible.",
            "Use the supplied reference_entry_hint when building the References section for sources actually cited.",
            "Where retrieved sources are insufficient for a claim, use a bracketed placeholder rather than inventing or forcing a citation.",
            "Do not invent page numbers, quotations, findings, or reference-list details not present in the metadata or supplied by the student.",
            "Maintain a clean thesis structure: use the selected chapter sections in order, keep subheadings purposeful, and do not move paragraphs outside their correct section.",
            "Use natural scholarly variation without disrupting logic, citations, tables, equations, references or section numbering.",
            "Minimise em dashes and en dashes. Prefer commas, semicolons, colons, parentheses, or separate sentences.",
            "Only bracketed attention placeholders should require user attention, such as [insert current statistic], [verify source], [confirm sample size], or [provide supervisor-approved wording]."
        ],
    }


def _human_scholarly_style_requirements(seed: Optional[int] = None) -> dict[str, list[str]]:
    """Return protected scholarly-humanizer rules for generation prompts."""
    return {"humanizer_rules": scholarly_humanizer_prompt_rules()}


def _student_contribution_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    """Return user-supplied human contribution and writing-style controls."""
    contribution = profile.get("student_contribution") or {}
    if not isinstance(contribution, dict):
        contribution = {}
    return {
        "draft_maturity": contribution.get("draft_maturity") or profile.get("draft_maturity") or "Supervisor-ready draft",
        "central_argument": contribution.get("central_argument") or "",
        "local_context_notes": contribution.get("local_context_notes") or "",
        "evidence_anchors": contribution.get("evidence_anchors") or "",
        "supervisor_comments": contribution.get("supervisor_comments") or "",
        "preferred_style": contribution.get("preferred_style") or "",
        "writing_sample": contribution.get("writing_sample") or "",
        "phrases_to_avoid": contribution.get("phrases_to_avoid") or "",
        "human_revision_pass_requested": bool(contribution.get("human_revision_pass", True)),
        "humanizer_mode": _humanizer_mode(profile),
        "paragraph_development_protocol": [
            "Before writing each substantive paragraph, identify the paragraph purpose, the evidence or user input available, the interpretation required, and the link to the study objective.",
            "Use the student's project-specific context, evidence anchors, supervisor comments, and preferred style wherever supplied.",
            "If a confident claim cannot be supported after checking the project profile, supplied evidence and source bank, qualify or omit it. Add one precise ACTION REQUIRED item only when a material user-only fact is essential.",
            "Avoid over-polished, perfectly balanced, template-like prose. Use natural scholarly reasoning, varied sentence structure, and context-specific transitions.",
            "Use controlled scholarly variation in practical terms: vary rhythm, sentence openings and paragraph shape only when the argument requires it, while preserving clarity, evidence and disciplinary precision.",
            "Where a writing sample is supplied, use it only to infer broad tone, sentence rhythm and level of directness; do not copy wording or imitate personal details.",
            "Make the draft sound like it has passed through a careful supervisor-student revision process: specific, cautious, evidenced and reflective, not generic or promotional.",
            "Do not add a visible AI-detection or humanisation note to the chapter; the chapter should read as an ordinary academic draft.",
        ],
        "generic_language_to_avoid": [
            "in today's world", "it is important to note", "delve into", "plays a crucial role",
            "various factors", "significant impact used vaguely", "this highlights the importance",
            "this study aims to contribute used vaguely", "moreover repeated mechanically",
            "furthermore repeated mechanically", "the research problem is that",
        ],
    }



def _supplementary_methods_guide_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    """Return generic rules for Chapter 7 as a practical guide.

    This must not hard-code any sample topic, sample constructs, sample items or sample sources.
    The user's previous output is treated only as a formatting and quality guide.
    """
    return {
        "document_type": "Supplementary Methods and Analysis Guide, not a formal thesis chapter",
        "sample_output_policy": [
            "Treat any attached/sample supplementary-methods output only as a guide to structure, table compactness and expected level of detail.",
            "Do not copy, hard-code or reuse the sample study title, sample constructs, sample item codes, sample sources, locations or sector unless the current project profile supplies the same details.",
            "Generate all constructs, items, variable names, analysis outputs and source suggestions from the current project profile, selected objectives, user answers, uploaded materials and source bank.",
        ],
        "primary_purpose": [
            "help the user prepare for data collection and analysis",
            "help develop or refine instruments, questionnaires, interview guides, item banks or coding guides",
            "map objectives to constructs, variables, measures, data sources and statistical outputs",
            "document scale/source traceability and adaptation decisions",
            "prepare coding, index construction, reliability, validity and analysis-output checklists",
            "organise appendix materials without overcrowding the main methodology chapter",
        ],
        "recommended_sections": [
            "Purpose and How to Use This Guide",
            "Study Inputs to Confirm Before Data Collection or Analysis",
            "Objective-to-Construct/Variable and Objective-to-Analysis Alignment",
            "Instrument, Scale and Source Traceability Guide",
            "Draft Questionnaire/Interview Item Bank or Coding Schedule",
            "Variable Coding, Transformation and Index Construction Notes",
            "Analysis Plan, Output Checklist and Decision Rules",
            "Validation, Reliability and Data Quality Checklist",
            "Appendix, Dataset and Evidence File Checklist",
            "References and Source/Scale Traceability Note",
        ],
        "source_and_scale_rules": [
            "Use the project source bank first when suggesting sources for instruments, scales, measures, operational definitions, data sources and analysis methods.",
            "If a source-bank record clearly contains or reports a validated scale/instrument, label it as a candidate validated scale to review/adapt.",
            "If a source-bank record supports the concept but does not provide a measurement instrument, label it as conceptual support only.",
            "If the source bank does not contain a verified scale source for a construct, insert an attention placeholder such as [insert verified scale source for this construct] instead of inventing a source.",
            "Do not include fixed example sources, sample sectors, sample constructs or sample study contexts unless those details appear in the user's current project profile, uploaded materials or source bank.",
            "Do not reproduce copyrighted scale items. Where an existing scale is only identified by name, provide an adaptation note and ask the user to verify the exact items from the original source.",
        ],
        "table_design_rules": [
            "Use compact markdown tables with five columns or fewer.",
            "Split wide tables into smaller tables instead of one crowded table.",
            "Keep table cells concise; place explanations below the table in prose.",
            "Never insert transition words inside item codes, table rows, scale points, formulas or equations.",
            "Use short headings such as Objective, Construct, Items, Output needed and Action required.",
            "For item banks, use columns such as Item code, Draft item, Response scale, Source/adaptation note and Action required.",
            "For analysis plans, use columns such as Objective, Variables, Statistical output needed, Decision rule and Attention item.",
        ],
        "tone_and_structure_rules": [
            "Use practical guide language rather than thesis-chapter narrative.",
            "Do not write 'Chapter Seven', 'this chapter', or long literature-review style paragraphs unless the user explicitly asks for a formal chapter.",
            "Use 'this guide', 'this analysis guide' or 'this supplementary guide'.",
            "Keep prose concise and action-oriented, with tables and checklists carrying most of the detail.",
            "Keep all red/attention material as bracketed placeholders only.",
        ],
    }


def _chapter_specific_requirements(chapter_number: int) -> list[str]:
    """Return chapter-level drafting rules that apply beyond section rules."""
    common = [
        "Use valid markdown for headings, paragraphs, lists, and tables.",
        "Keep paragraphs coherent and academic, with clear topic sentences, developed reasoning, and smooth transitions.",
        "Write with a natural, polished academic voice rather than a template-like or mechanical tone.",
        "Make the chapter read as a coherent scholarly argument, not a collection of disconnected notes.",
        "Avoid generic filler, excessive repetition, unsupported claims, vague expressions, and very short choppy sentences.",
        "Treat the chapter as part of a completed project, dissertation, or thesis. Do not use future-tense proposal wording such as 'will examine', 'will collect', 'will use', 'will adopt', 'will analyse', or 'will be conducted'.",
        "Do not mention that the writing is designed to meet a selected academic level, checklist, template, or software requirement. The chapter should read like normal scholarly prose.",
    ]

    if chapter_number == 1:
        return common + [
            "Frame the statement of the problem through evidence, contradiction, gap, or unresolved practical concern rather than beginning with 'The research problem is that...'.",
            "Use connected paragraphs that move from context to evidence, evidence to gap, and gap to research focus.",
            "Use accurate statistics and factual evidence from supplied or automatically retrieved sources where available. If an exact figure remains unavailable, write the defensible non-numeric point and add one precise ACTION REQUIRED item only when the figure is essential.",
        ]

    if chapter_number == 2:
        return common + [
            "Organise the literature review around the student's selected structure and research objectives.",
            "Where a literature gap table is requested, create a clean markdown table, not a paragraph.",
            "Use this exact table structure for a literature gap table: | Research Objective | Key Authors and Year | Context of Study | Method Used | Key Findings | Identified Gap | Relevance to Current Study |.",
            "Each research objective should have at least one separate row in the literature gap table.",
            "Use concise table entries. Do not merge all studies, methods, findings, and gaps into one long cell.",
            "Where the student has not supplied authors or studies, use placeholders such as [insert author and year] rather than inventing sources.",
            "For conceptual framework sections, do not create messy ASCII diagrams. Present a clean relationship table and, where a diagram is needed, provide a simple Mermaid flowchart code block that can be rendered later.",
            "Explain the conceptual framework in prose after the table or diagram, including independent, dependent, mediating, moderating and control variables where applicable.",
        ]

    if chapter_number == 3:
        return common + [
            "Write Chapter Three as a completed final project, dissertation, or thesis chapter, not as a proposal.",
            "Use past tense and completed-study wording throughout Chapter Three, for example: 'the study adopted', 'data were collected', 'respondents were selected', 'the questionnaire was administered', and 'the data were analysed'.",
            "Do not use proposal-style future tense such as 'will adopt', 'will collect', 'will be used', 'will be analysed', 'will be administered', 'will be obtained', or 'will be conducted'.",
            "If a detail has not been supplied, use a past-tense placeholder, for example '[insert sampling procedure used]' or '[insert data collection period]', not future-tense wording.",
            "Maintain consistency among philosophy, approach, design, sampling, instrument, validity, reliability, analysis, and ethics.",
            "The methodology chapter should follow a strong doctoral-methods structure: introduction, research philosophy, research approach, study design, target population, sample size and sampling procedure, operationalisation and measurement, sources of data, data collection instrument, reliability and validity, ethical considerations, and data processing and analysis.",
            "For primary survey studies, include common method variance and social desirability safeguards, including procedural remedies such as varied scale formats, careful item ordering, anonymity, and statistical checks where applicable.",
            "Use a variable or construct operationalisation table where measurement is discussed, with columns: Variable/Concept, Indicator/Dimension, Operational Indicator, Item Scale, Level of Measurement, and Origin/Source.",
            "Use an analysis-plan table where data analysis is discussed, with columns: Research Objective, Research Question/Hypothesis, Analytical Technique, Ex-Ante Assumptions, Post-Estimation/Analysis Checks, and Decision Rule.",
            "When model equations are needed, present each equation in a separate display equation block using double dollar delimiters. Prefer clean Word-friendly mathematical notation using Unicode Greek letters and subscripts where possible, for example SDᵢ = β₀ + β₁PCRᵢ + ∑ₖ₌₁ᵐ βₖCVₖᵢ + εᵢ. Define all variables directly below the equation.",
        ]

    if chapter_number == 4:
        return common + [
            "Write a clean Results/Data Analysis and Discussion chapter. Do not refer to the file as 'uploaded results', 'the uploaded output', 'the output uploaded', or similar; convert the supplied output into normal thesis prose and tables.",
            "Study any supplied results, statistical output, qualitative coding output, Excel tables, SPSS/Stata/R output, or analysis notes and reorganise them into a coherent chapter aligned with the methods and objectives.",
            "Create all required tables that match the research methods, objectives, questions and hypotheses: response/profile table, descriptive statistics, reliability/validity where applicable, assumptions/diagnostics, objective-by-objective results, model estimates/path coefficients/regression/econometric tables, qualitative theme tables, and hypothesis decision tables where relevant.",
            "Use only results actually supplied in uploaded files or student answers. Do not invent coefficients, p-values, sample sizes, reliability values, model fit statistics, themes, quotations or percentages.",
            "Where a required result is missing, create a clean placeholder table with bracketed attention placeholders such as [insert regression coefficients and p-values here] and add a short advisory sentence telling the user the exact result/output to obtain.",
            "Where a figure, graph, conceptual/path diagram or visual result is required but missing, insert a bracketed attention placeholder such as [insert Figure 4.1: Conceptual/path diagram or chart here] and state the output needed to create it.",
            "Advise what should go to appendix, including raw software output, long diagnostics, full correlation matrices, full interview transcripts, questionnaires, codebooks and lengthy robustness checks. Keep the main text clean.",
            "Map each result to the relevant research objective, question or hypothesis before discussing it.",
            "Interpret results beyond description and link discussion to theory, prior studies and context using relevant citations.",
        ]

    if chapter_number == 5:
        return common + [
            "Base summaries, conclusions, recommendations, and future research suggestions only on supplied findings.",
            "Ensure each recommendation can be traced to a finding.",
        ]

    if chapter_number == 6:
        return common + [
            "Treat this as a user-specified additional chapter. Use the user's requested headings, scope and evidence requirements as the organising structure.",
            "Do not force standard Chapter One to Chapter Five content into this custom chapter unless the user requests it.",
            "Keep the chapter aligned with the overall project title, objectives, theory, method, results and recommendations.",
        ]

    if chapter_number == 7:
        return [
            "Treat this output as a Supplementary Methods and Analysis Guide, not as a formal thesis chapter for submission.",
            "The guide is a working document for the student, supervisor and analyst. It should help with instrument development, scale/source traceability, coding, reliability and validity checks, analysis planning, and appendix organisation.",
            "Do not write 'Chapter Seven', 'this chapter', or formal chapter-style narrative unless the user explicitly asks. Use 'this guide', 'this analysis guide', or 'this supplementary guide'.",
            "Any attached/sample output is only a guide to structure and level of detail. Do not copy or hard-code its title, topic, constructs, items, sources, sector, location or wording into the current output.",
            "Generate the guide from the current project profile, objectives, questions/hypotheses, variables/constructs, uploaded files, user answers and source bank.",
            "For primary survey or mixed-method studies, include objective-to-construct alignment, item development, source traceability, proposed questionnaire/interview items, suggested response scales, coding notes, validation checks and analysis outputs needed.",
            "For secondary, econometric, time-series or panel studies, include a variable/data-source register, operational definitions, expected signs, transformations, coding notes, data-quality checks and model-output checklist.",
            "Use the project source bank first for instrument/scale suggestions. If a verified or validated scale source is available in the source bank or uploaded notes, cite it beside the relevant construct as a candidate source to review/adapt.",
            "Where no verified scale source is supplied, use an attention placeholder such as [insert verified scale source for this construct] rather than naming a generic or sample source.",
            "Clearly distinguish validated scale source, conceptual support, method/source guidance, contextual support, and project-specific evidence.",
            "Do not claim that a scale has been adopted unless the current project profile or source bank confirms adoption. Use wording such as 'candidate source to review/adapt' or 'conceptual support only' where appropriate.",
            "Use compact markdown tables with not more than five columns. Split wide tables into smaller tables instead of forcing one large table across the page.",
            "Use short column headings and concise cells. Avoid long paragraphs inside table cells; put explanations below the table as prose.",
            "Do not insert transition words such as 'Indeed', 'Conversely', 'Still', 'Yet' or 'Importantly' inside item codes, table rows, scale points, formulas, equations or lists.",
            "Use clean item-bank tables with columns such as Item code, Draft item, Response scale, Source/adaptation note and Action required.",
            "Use clean analysis-plan tables with columns such as Objective, Variables, Statistical output needed, Decision rule and Attention item.",
            "Where a questionnaire scale, data source, period, frequency, code, transformation, permission note or validation output is missing, insert a bracketed attention placeholder such as [insert verified scale source for this construct] or [confirm coding rule].",
            "Include a References section only for sources actually cited in the guide, followed by a short Source and Scale Traceability Note if source-search records were attached.",
        ]

    return common


def _effective_chapter_title(chapter: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    """Return the chapter title used in prompts and fallback drafts."""
    if int(chapter_number or 0) == 6:
        custom_title = str(profile.get("other_chapter_title") or "").strip()
        if custom_title:
            return custom_title
        return "Others"
    if int(chapter_number or 0) == 7:
        return "Supplementary Methods and Analysis Guide"
    return str(chapter.get("chapter_title") or "").strip() or "Chapter"


def build_drafting_prompt(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
) -> str:
    chapter = get_chapter(chapter_number)
    effective_chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}
    chapter_length_requirements = _chapter_length_requirements(
        profile, chapter_number, [section.get("section_id", "") for section in sections]
    )

    section_payload = []
    for section in sections:
        section_payload.append(
            {
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "guiding_questions": section.get("guiding_questions", []),
                "rules": section.get("rules", []),
                "student_answers": answers.get(section["section_id"], {}),
            }
        )

    prompt_profile = {
        key: value
        for key, value in profile.items()
        if key not in {"source_bank", "attached_sources", "retrieved_sources", "previous_chapters_context", "uploaded_alignment_chapters"}
    }

    prompt = {
        "task": "Develop an editable academic working draft from the user's own research inputs and selected institutional guideline sections.",
        "chapter": {
            "chapter_number": chapter_number,
            "chapter_title": effective_chapter_title,
        },
        "project_profile": prompt_profile,
        "selected_academic_level_and_depth": _level_depth_requirements(profile),
        "chapter_page_word_and_citation_targets": chapter_length_requirements,
        "level_based_model_quality_route": _model_route_for_prompt(profile, chapter_number),
        "reference_currency_requirements": _reference_currency_requirements(),
        "citation_and_evidence_requirements": _citation_and_evidence_requirements(chapter_number),
        "institutional_format_requirements": _institutional_format_requirements(profile, chapter_number),
        "human_scholarly_style_requirements": _human_scholarly_style_requirements(seed=hash(profile.get("title", "")) & 0xFFFFFFFF),
        "student_contribution_and_style_controls": _student_contribution_requirements(profile),
        "draft_grounding_and_provisional_mode": _has_meaningful_user_inputs(profile, answers),
        "analysis_evidence_for_this_chapter": _uploaded_results_for_chapter(profile, chapter_number),
        "previous_chapters_for_alignment": _previous_chapters_for_alignment(profile, chapter_number),
        "retrieved_sources": _retrieved_sources_for_prompt(profile, chapter_number),
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "chapter_specific_requirements": _chapter_specific_requirements(chapter_number),
        "supplementary_methods_guide_requirements": _supplementary_methods_guide_requirements(profile) if int(chapter_number or 0) == 7 else {},
        "output_requirements": [
            "Write in formal British English.",
            "Use the selected academic level internally to determine depth and sophistication, but never mention the selected level in the generated chapter text.",
            "Follow the level_based_model_quality_route: the user is paying for guided working-draft development, so the main prose must be academically strong at the selected level; do not produce low-tier, shallow or mechanical writing.",
            "Follow chapter_page_word_and_citation_targets. Aim to finish within its minimum and maximum word range, distribute the target across selected sections using section_word_budgets, and do not stop after a brief overview.",
            "Meet the depth target through evidence, synthesis, comparison, critique, methodological explanation, interpretation and study-specific application. Never meet it through repetition, generic padding, duplicated definitions or inflated wording.",
            "Use the stated citation-occurrences-per-1,000-words range as a planning guide. Increase citation density across substantive paragraphs while preserving strict relevance and source integrity.",
            "Follow the human_scholarly_style_requirements and student_contribution_and_style_controls so the writing sounds natural, rigorous, context-specific, evidence-led and carefully supervised rather than generic or mechanical.",
            "In all generated chapters, use protected scholarly variation: natural sentence and paragraph rhythm, context-specific transitions and moderate lexical variety without sacrificing clarity, evidence, APA accuracy or methodological precision.",
            "Use the student's central argument, local context notes, evidence anchors, supervisor comments, preferred writing style and supplied writing sample as style/context guidance; do not copy the writing sample verbatim unless the user has written it as content to include.",
            "Use an evidence-to-paragraph method: each substantive paragraph should have a purpose, a claim grounded in supplied evidence or source-bank material, interpretation, and a clear link to the objective or chapter argument.",
            "Before producing a long paragraph, check whether the project profile, attached evidence, automatically retrieved sources or defensible general knowledge support it. Complete what can be responsibly completed. If a material claim still lacks support, shorten or qualify it and add one precise ACTION REQUIRED item only when the user must supply something unavailable to the system.",
            "Make the writing high-quality and human-supervised by adding discipline-specific reasoning, careful qualifications, context-specific transitions and clear links between evidence and the student's own objectives.",
            "Where the user has supplied limited information, still prepare a draft for the user's consideration, but label uncertainty through bracketed attention placeholders and avoid pretending the draft is fully grounded.",
            "In provisional drafting, develop the strongest defensible draft from the title, research area, objectives, study design, context, available source bank and automatically retrieved evidence. Do not turn every missing detail into a placeholder.",
            "Reserve ACTION REQUIRED items for unique, material inputs that only the user, supervisor or institution can provide, such as the exact study population, site, sample, approved instrument, ethics approval, study period or actual results. Do not repeat an action already stated earlier.",
            "Respect the selected draft maturity: a structured draft can be more schematic; a supervisor-ready or revised academic draft must be more developed, but still grounded in user-supplied evidence and sources.",
            "Avoid very short sentences except where they are necessary for emphasis, transition, or clarity.",
            "Do not write sentences that say the work, chapter, section, depth, or argument is designed to meet the selected level of the project, thesis, or dissertation.",
            "Use the reference_currency_requirements: aim for at least 70% of substantive references within the stated recent-reference window, but where current sources do not exist, use the strongest credible available sources instead.",
            "Use the citation_and_evidence_requirements: include relevant, accurate in-text citations across all substantive write-up sections, especially literature, methodology justification, discussion, and problem framing.",
            "Follow institutional_format_requirements. For Chapter One, apply its background_structure and purpose_statement_style exactly, and use expected_chapters for Organisation of the Study.",
            "Do not create an action asking the user to approve a general objective, purpose statement, chapter count or basic wording that can be derived from the project profile. Draft it cleanly for the user's consideration.",
            "For Chapter Two and every later chapter, use previous_chapters_for_alignment to check consistency with earlier chapters before writing. Align concepts, variables, theories, objectives, research questions, hypotheses, methodology and terminology with the supplied earlier chapters.",
            "Do not copy large passages from previous_chapters_for_alignment. Use it to detect contradictions, omissions and missing links. Where alignment cannot be confirmed, insert a precise bracketed attention placeholder such as [confirm alignment with Chapter One objective wording].",
            "Use retrieved_sources as an additional evidence bank where the user has run the source finder. Do not replace the project profile, user-provided evidence, uploaded files, or placeholders; enrich the draft with relevant retrieved sources.",
            "When retrieved_sources contains sources marked highly_relevant or partly_relevant, review them carefully and integrate those that directly support the chapter argument. Do not cite not_relevant sources, and do not cite any source merely to increase citation count.",
            "Every chapter must end with one clean References section containing complete entries only for sources cited in the chapter body. Use available reference_entry_hint/apa_hint details, remove duplicates, omit bullets and numbering, and alphabetise entries by the first author or institutional author.",
            "Increase in-text citation density in line with the stronger level-specific planning range. Chapter One should support most substantive background and problem paragraphs with directly relevant citations; Chapter Two should be citation-rich and synthesise multiple studies in most substantive paragraphs; Chapter Three should cite methodological and measurement authorities where appropriate; Chapter Four discussion should cite theory and directly comparable studies.",
            "If the user did not manually attach sources, use the automatically enriched source bank when available. A source may be cited more than once only when it directly supports each claim. Never use a citation merely as decoration.",
            "Run a claim-evidence pass before finalising. Every substantive factual, historical, policy, contextual, theoretical or empirical claim must be supported by a directly relevant and accurate citation from the supplied or retrieved evidence bank. Do not leave long substantive paragraphs without support.",
            "For Chapter One, follow the level-specific citation range in chapter_page_word_and_citation_targets. Support substantive contextual, theoretical, policy, historical and empirical claims throughout the section, not only at paragraph endings. Accuracy and direct relevance remain more important than numerical padding.",
            "Do not embed instructions, confirmations or missing-evidence commentary inside academic prose. Put each unresolved item on its own bracketed line beginning [ACTION REQUIRED: ...] immediately after the sentence or paragraph that requires the action, so the full instruction is exported in red at the exact point of need.",
            "If retrieved_sources do not provide enough support for a required claim, insert a bracketed placeholder such as [insert verified source for this claim] rather than guessing.",
            "For Chapter One, make the Background and Statement of the Problem factual and evidence-led. Use relevant accurate statistics, policy evidence, institutional evidence, or empirical findings to support the problem where supplied or confidently known.",
            "Do not fabricate citations, statistics, or reference-list entries. Use verified/supplied citations and facts where available. Where a required source, statistic, or fact is not supplied or cannot be stated confidently, insert a bracketed placeholder rather than inventing it.",
            "Use clear numbered headings matching the selected sections.",
            "For Research Objectives and Research Questions sections, restart the ordered list at 1 within each section. Do not continue numbering from a previous section.",
            "Do not attach explanatory commentary, level-alignment notes, methodological justification or summary prose after research objectives or research questions. Return clean standalone numbered items only. Discard generated commentary rather than converting it into an action item.",
            "Use a thesis-style hierarchy: Chapter title, major sections such as 1.1, 1.2 and 1.3, and lower-level subheadings such as 1.2.1 only where they genuinely improve clarity.",
            "Do not merge selected sections. Present each selected section and subsection in the same logical order as the approved guideline/template.",
            "Do not use raw HTML colour tags such as <span style=...>. Do not colour normal academic prose; only attention placeholders should be highlighted by the DOCX exporter. The only text requiring user attention should appear as bracketed placeholders such as [insert current statistic], [verify citation], [confirm sample size], or [provide supervisor-approved wording].",
            "Minimise the use of em dashes and en dashes. Use commas, semicolons, colons, parentheses, or separate sentences instead unless a dash is unavoidable.",
            "Draft only the selected sections.",
            "Treat the output as an AI-assisted editable working draft developed from user-supplied research inputs. Never call it final, completed, submission-ready, ghostwritten or independently authored by ProjectReady AI.",
            "The user remains responsible for authorship, source verification, factual accuracy, ethical compliance, institutional requirements and final submission decisions.",
            "For the Supplementary Methods and Analysis Guide, use any attached/sample output only as a guide to structure and table compactness. Do not copy its topic, constructs, sources, item wording or sample context unless those details are supplied in the current project profile.",
            "For the Supplementary Methods and Analysis Guide, suggest verified scale/instrument sources only from the current source bank, uploaded materials or verified project notes. If a verified source is not available, use [insert verified scale source for this construct].",
            "For the Supplementary Methods and Analysis Guide, make the output practical: alignment tables, item banks, coding notes, analysis-output checklist, reliability/validity checklist and appendix checklist should carry the detail.",
            "Use analytical and connective prose: show why each point matters to the study rather than merely naming concepts, authors, variables, or methods.",
            "Avoid weak or unscholarly problem-statement phrasing such as 'The research problem is that...'. Use an evidence-led academic formulation instead.",
            "Write as a completed academic project, dissertation, or thesis. Avoid proposal-style future tense across the write-up, except where Chapter Five legitimately suggests future research using 'should', 'could', or 'may'.",
            "Prefer precise, discipline-appropriate wording over exaggerated claims or promotional language.",
            "Do not invent fabricated references, statistics, ethical approvals, sample sizes, or data results.",
            "Where evidence is missing, write a bracketed placeholder such as [insert recent empirical evidence].",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "Use markdown tables only where a table is clearly requested or useful.",
            "Use APA 7th style for the chapter References section. Include only sources cited in the chapter body. Present one clean, complete, deduplicated and alphabetised entry per paragraph, without bullets, numbering, annotations, relevance labels, source keys or a Source Use Audit.",
            "When equations are required, place each equation in a display equation block using the format $$ equation $$. Use clean Word-friendly mathematical notation where possible, with Unicode Greek letters and subscripts rather than raw LaTeX commands. Do not leave important equations only as ordinary text.",
            "For conceptual framework diagrams, avoid messy ASCII art. Use a clean relationship table and, where appropriate, a Mermaid flowchart code block. Keep the diagram simple enough to be readable.",
            "When revision mode is enabled, preserve the original structure as far as possible, revise with comments in the narrative where helpful, and preserve the original structure. Do not wrap ordinary inserted material in colour markers; use bracketed attention placeholders only where the student must verify or complete something.",
            "For Chapter Two tables, use a properly structured markdown table with meaningful column headers and one idea per cell.",
            "For Chapter Three, use past tense for completed project work and avoid future-tense proposal wording.",
            "For Chapter Four, transform supplied result files and answers into a clean thesis chapter. Do not write phrases such as 'the uploaded results', 'uploaded output', 'the output uploaded', or 'the attached file shows'. Present the tables and narrative as normal Results/Data Analysis and Discussion content.",
            "For Chapter Four, create the tables required by the selected methodology and objectives. If a required table cannot be completed from the supplied results, create a placeholder markdown table with bracketed attention placeholders and advise the user exactly which output to obtain.",
            "For Chapter Four, insert bracketed attention placeholders for required missing figures, graphs, path diagrams, conceptual diagrams or charts, and advise whether they belong in the main chapter or appendix.",
            "For Chapter Four, advise which materials should move to appendices, such as raw software output, lengthy diagnostic tables, full correlation matrices, full questionnaires, interview transcripts, codebooks and robustness checks.",
            "For Chapter Four, report only results found in uploaded files or student answers. Do not fabricate numbers, tables, themes, or interpretation.",
            "For the Research Methods/Methodology chapter, produce a substantial, coherent methodology working draft suitable for supervisor review. Do not present it as a planning note, upload summary, worksheet, or supplementary file.",
            "For questionnaire or interview-guide outputs, build draft instruments from the constructs, variables and objectives supplied in the project profile rather than giving only a generic structure.",
            "Keep a clear distinction between the main Research Methods/Methodology chapter and the Supplementary Methods and Analysis Guide. The main methodology chapter is the coherent editable working draft; the supplementary guide is a practical planning guide for instruments, data sources, scale traceability, coding, validation checks and appendix materials.",
            "Do not overload the main Research Methods/Methodology chapter with a full questionnaire, interview guide, scale bank, secondary-data register, or data-source codebook. Those details belong in the separate Supplementary Methods and Analysis Guide or appendix unless the institution specifically requires them in the main chapter.",
            "For Chapter Five, base conclusions and recommendations only on findings supplied in the profile or answers.",
        ],
    }
    return json.dumps(prompt, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# HUMANISER POST-PROCESSING FUNCTIONS
# ----------------------------------------------------------------------

def _humanizer_mode(profile: Optional[dict[str, Any]] = None) -> str:
    """Resolve the requested humanizer mode from the project profile or environment."""
    contribution = (profile or {}).get("student_contribution") or {}
    requested = ""
    if isinstance(contribution, dict):
        requested = str(contribution.get("humanizer_mode") or "").strip().lower()
    if not requested:
        requested = str((profile or {}).get("humanizer_mode") or "").strip().lower()
    if not requested:
        requested = str(os.getenv("PROJECTREADY_HUMANIZER_MODE", "balanced") or "balanced").strip().lower()
    return requested if requested in {"off", "light", "balanced", "deep"} else "balanced"


def _increase_natural_variation(text: str) -> str:
    """Compatibility wrapper for the protected local scholarly humanizer."""
    return humanize_scholarly_text(text, mode="balanced")[0]


def _enforce_burstiness(text: str, target_std_dev: float = 12.0, max_uniform: int = 3) -> str:
    """Compatibility wrapper. Natural variation is now evidence-preserving and deterministic."""
    return text or ""


def _add_drafting_artefacts(text: str, probability_per_500_words: float = 0.25) -> str:
    """Retained for compatibility. Artificial drafting artefacts are no longer inserted."""
    return text or ""


def _boost_lexical_richness(text: str, replacement_probability: float = 0.5) -> str:
    """Retained for compatibility. Mechanical synonym replacement is no longer used."""
    return text or ""


def _cluster_citations(text: str) -> str:
    """Keep citation clusters only when the sources already exist; never fabricate authors."""
    return text or ""


def _inject_tangent(text: str) -> str:
    """Compatibility hook. Do not inject unrelated examples or unsupported tangents."""
    return text or ""


def _randomise_paragraph_order(text: str) -> str:
    """Compatibility hook. Keep thesis sections and paragraphs in their approved order."""
    return text or ""


def _vary_paragraph_openings(text: str) -> str:
    """Compatibility hook. Paragraph-opening refinement is handled by the protected humanizer."""
    return text or ""


def _force_short_sentences(text: str, target_every_n_words: int = 200) -> str:
    """Retained for compatibility. Short sentences are not forced mechanically."""
    return text or ""


def _humanize_with_small_model(text: str, model: str = "llama3-8b-8192") -> str:
    """Optional compatibility pass that never introduces deliberate errors.

    The main application uses the OpenAI revision pass and the deterministic local
    humanizer. This Groq path remains opt-in for older deployments.
    """
    if not text or len(text) < 200:
        return text
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or os.getenv("PROJECTREADY_ENABLE_GROQ_HUMANIZER", "0").strip().lower() not in {"1", "true", "yes"}:
        return text
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except Exception:
        return text

    prompt = f"""Revise the academic prose below for clarity, natural scholarly rhythm and discipline-appropriate wording.
Preserve every fact, statistic, date, citation, reference, heading, equation, table and bracketed placeholder exactly.
Do not add deliberate mistakes, fragments, casual language, new claims, new citations or commentary.
Return only the revised text.

Text:
{text}"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000,
        )
        candidate = str(response.choices[0].message.content or "").strip()
        valid, _ = validate_humanizer_preservation(text, candidate, max_word_change_ratio=0.04)
        return candidate if candidate and valid else text
    except Exception:
        return text


def _add_human_noise(text: str, error_probability: float = 0.02) -> str:
    """Compatibility hook. Deliberate surface noise is permanently disabled."""
    return text or ""


def _polish_generated_text(text: str) -> str:
    """Lightly remove common proposal/meta phrases that weaken scholarly output."""
    if not text:
        return text

    replacements = {
        r"\bThe research problem is that\b": "The central concern is that",
        r"\bthe research problem is that\b": "the central concern is that",
        r"\bThis is done to meet the level of the project\b": "",
        r"\bThis is done to meet the level of the thesis\b": "",
        r"\bThis is done to meet the level of the dissertation\b": "",
        r"\bto meet the selected academic level\b": "",
        r"\bto satisfy the selected academic level\b": "",
        r"\bfor the selected academic level\b": "",
        r"\bwill be used\b": "was used",
        r"\bwill be adopted\b": "was adopted",
        r"\bwill be employed\b": "was employed",
        r"\bwill be collected\b": "were collected",
        r"\bwill be analysed\b": "were analysed",
        r"\bwill be analyzed\b": "were analysed",
        r"\bwill be conducted\b": "was conducted",
        r"\bwill be administered\b": "was administered",
        r"\bwill be obtained\b": "was obtained",
        r"\bwill use\b": "used",
        r"\bwill adopt\b": "adopted",
        r"\bwill employ\b": "employed",
        r"\bwill collect\b": "collected",
        r"\bwill analyse\b": "analysed",
        r"\bwill analyze\b": "analysed",
        r"\bwill administer\b": "administered",
        r"\bwill examine\b": "examined",
        r"\bwill assess\b": "assessed",
        r"\bwill investigate\b": "investigated",
        r"\bwill determine\b": "determined",
        r"\bthe uploaded results show\b": "the results show",
        r"\bthe uploaded output shows\b": "the results show",
        r"\bthe output uploaded shows\b": "the results show",
        r"\bthe attached results show\b": "the results show",
        r"\bin today's world\b": "in the present context",
        r"\bit is important to note that\b": "",
        r"\bdelve into\b": "examine",
        r"\bplays a crucial role\b": "is important",
        r"\bvarious factors\b": "specific factors",
        r"\bit is imperative\b": "it is necessary",
        r"\bfrom the uploaded results\b": "from the results",
        r"\bfrom the uploaded output\b": "from the results",
        r"\bfrom the attached output\b": "from the results",
        r"\buploaded results\b": "results",
        r"\buploaded output\b": "results",
    }
    polished = text
    for pattern, replacement in replacements.items():
        polished = re.sub(pattern, replacement, polished, flags=re.IGNORECASE)

    polished = re.sub(
        r"(?im)^.*(?:selected academic level|level of the project|level of the thesis|level of the dissertation|checklist requirement|template requirement|software requirement).*\n?",
        "",
        polished,
    )

    polished = re.sub(r"[ \t]{2,}", " ", polished)
    polished = re.sub(r"\n{3,}", "\n\n", polished)
    return polished.strip()




# ----------------------------------------------------------------------
# FINAL OUTPUT CONTROLS
# ----------------------------------------------------------------------

_ATTENTION_RE = re.compile(
    r"\[(?:insert|verify|confirm|provide|supply|complete|replace|check|add|update|obtain|state|specify|include)\b[^\]]*\]",
    flags=re.IGNORECASE,
)


def _strip_colour_markup(text: str) -> str:
    """Remove raw colour HTML/markers so only exporter controls red attention text."""
    if not text:
        return text
    text = re.sub(r"<span\s+[^>]*color\s*:\s*#?(?:c00000|ff0000|red)[^>]*>(.*?)</span>", r"\1", text, flags=re.I | re.S)
    text = re.sub(r"</?span[^>]*>", "", text, flags=re.I)
    text = text.replace("[[ADD]]", "").replace("[[/ADD]]", "")
    return text


def _minimise_em_en_dashes(text: str) -> str:
    """Reduce em/en dashes in generated prose while preserving ordinary hyphenated terms."""
    if not text:
        return text
    text = text.replace("—", ", ")
    text = text.replace(" – ", ", ")
    text = text.replace("–", "-")
    text = text.replace("‑", "-")
    text = re.sub(r"\s+,\s+", ", ", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _normalise_attention_language(text: str) -> str:
    """Keep only attention placeholders as attention text; do not label ordinary prose as red."""
    if not text:
        return text
    text = re.sub(r"\bred\s+bracketed\s+placeholders?\b", "bracketed attention placeholder", text, flags=re.I)
    text = re.sub(r"\bred\s+placeholders?\b", "bracketed attention placeholder", text, flags=re.I)
    text = re.sub(r"\bin\s+red\s+text\b", "as a bracketed attention placeholder", text, flags=re.I)
    text = re.sub(r"\bred\s+text\b", "attention placeholder", text, flags=re.I)
    return text


def _protect_thesis_structure(text: str) -> str:
    """Light structural clean-up: keep heading spacing and remove duplicate blank lines."""
    if not text:
        return text
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?<![\n#])(#{1,4}\s+)", r"\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()



def _split_list_item_guidance(item_text: str, section_kind: str) -> tuple[str, str]:
    """Keep objectives/questions clean and move explanatory guidance to attention text."""
    text = re.sub(r"\s+", " ", str(item_text or "")).strip()
    if not text:
        return "", ""

    guidance_patterns = [
        r"\bThese objectives\b",
        r"\bThese questions\b",
        r"\bThe questions correspond\b",
        r"\bThe first objective\b",
        r"\bThe first question\b",
        r"\bThe second objective\b",
        r"\bThe second question\b",
        r"\bThe third objective\b",
        r"\bThe third question\b",
        r"\bThe fourth objective\b",
        r"\bThe fourth question\b",
        r"\bThe fifth objective\b",
        r"\bThe fifth question\b",
        r"\bThis objective\b",
        r"\bThis question\b",
        r"\bThis alignment\b",
        r"\bThis allowed\b",
        r"\bThis ensured\b",
    ]
    starts = [m.start() for pat in guidance_patterns for m in [re.search(pat, text, flags=re.I)] if m]
    if starts:
        pos = min(starts)
        main = text[:pos].strip()
        guidance = text[pos:].strip()
        return main.rstrip(), guidance

    # Research questions should end at the first question mark. Any prose after
    # that is usually explanation, not another question item.
    if section_kind == "questions":
        q = text.find("?")
        if q >= 0 and q + 1 < len(text):
            return text[: q + 1].strip(), text[q + 1 :].strip()

    # Objectives are usually one verb-led statement. If a second sentence is an
    # explanation rather than part of the objective, move it to guidance.
    if section_kind == "objectives":
        m = re.search(r"(\.(?:\s+|$))(The|These|This)\b", text)
        if m and m.start() > 20:
            return text[: m.start() + 1].strip(), text[m.start() + 1 :].strip()

    return text, ""


def _normalise_numbered_items_in_section(section_text: str, section_kind: str) -> str:
    """Return clean objective/question lists beginning at 1 without commentary."""
    if not section_text:
        return section_text

    attention_lines: list[str] = []
    items: list[str] = []
    section_kind = str(section_kind or "").strip().lower()

    def add_attention(value: str) -> None:
        value = re.sub(r"\s+", " ", value or "").strip()
        if value and value not in attention_lines:
            attention_lines.append(value)

    def add_item(value: str, *, was_numbered: bool = False) -> None:
        value = re.sub(r"\s+", " ", value or "").strip()
        value = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", value).strip()
        if not value:
            return
        main, _guidance = _split_list_item_guidance(value, "questions" if section_kind == "questions" else "objectives")
        main = re.sub(r"\s+", " ", main).strip()
        if not main:
            return
        # Explanatory prose generated after a list is intentionally discarded.
        if re.match(
            r"^(?:These objectives?|These questions?|The (?:first|second|third|fourth|fifth) "
            r"(?:objective|question)|This (?:objective|question|alignment)|The objectives? (?:support|enable|allow)|"
            r"The questions? (?:support|enable|allow))\b",
            main,
            flags=re.I,
        ):
            return
        if section_kind == "questions":
            if not was_numbered and not (
                main.endswith("?")
                or re.match(r"^(?:What|How|Why|Which|Who|Where|When|To what extent|Does|Do|Did|Is|Are|Was|Were|Can|Could|Would|Should)\b", main, re.I)
            ):
                return
            if not main.endswith("?"):
                main = main.rstrip(".") + "?"
        elif section_kind in {"objectives", "general_objective"}:
            if not was_numbered and not re.match(
                r"^(?:To\s+)?(?:assess|analyse|analyze|compare|determine|develop|establish|estimate|evaluate|examine|explore|identify|investigate|measure|test|describe|ascertain|explain|rank|map|conceptuali[sz]e)\b",
                main,
                flags=re.I,
            ):
                return
            main = main.rstrip(";")
        key = re.sub(r"[^a-z0-9]+", "", main.lower())
        if key and all(re.sub(r"[^a-z0-9]+", "", old.lower()) != key for old in items):
            items.append(main)

    # Make inline numbering such as "... ? 2. How ...? 3. What ...?" visible.
    normalised = re.sub(r"\s+(?=\d+[.)]\s+)", "\n", section_text)
    for raw_line in normalised.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if re.match(r"^\[[^\]]+\]$", stripped):
            add_attention(stripped)
            continue

        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
        body = numbered.group(2).strip() if numbered else stripped
        was_numbered = bool(numbered)

        if section_kind == "general_objective":
            add_item(body, was_numbered=True)
            if items:
                break
            continue

        if section_kind == "questions":
            # Split more than one question accidentally placed on the same line.
            chunks = [chunk.strip() for chunk in re.findall(r"[^?]+(?:\?|$)", body) if chunk.strip()]
            if len(chunks) > 1:
                for chunk in chunks:
                    add_item(chunk, was_numbered=was_numbered)
            else:
                add_item(body, was_numbered=was_numbered)
        else:
            add_item(body, was_numbered=was_numbered)

    if not items:
        # Avoid deleting unusual institution-specific content when no list can be identified.
        return section_text.strip()

    if section_kind == "general_objective":
        output = [items[0]]
    else:
        output = [f"{index}. {item}" for index, item in enumerate(items, start=1)]

    if attention_lines:
        output.extend(["", *attention_lines])
    return "\n".join(output).strip()


def _normalise_objectives_and_questions(text: str) -> str:
    """Restart objective/question numbering at 1 and remove generated list commentary."""
    if not text:
        return text
    heading_re = re.compile(
        r"(?im)^(#{1,4}\s*)?(?:\d+(?:\.\d+){0,3}\s+)?"
        r"(Research Objectives|General Objective|Specific Objectives|Research Questions|Research Question|Hypotheses)\s*$"
    )
    matches = list(heading_re.finditer(text))
    if not matches:
        return text

    parts: list[str] = []
    last = 0
    for idx, match in enumerate(matches):
        section_start = match.start()
        body_start = match.end()
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        next_heading = re.search(
            r"(?im)^\s*(?:#{1,4}\s+[^\n]{2,120}|\d+\.\d+(?:\.\d+)*\s+[A-Z][^\n]{2,120})$",
            text[body_start:next_start],
        )
        if next_heading:
            body_end = body_start + next_heading.start()
            tail_start = body_end
        else:
            body_end = next_start
            tail_start = next_start

        heading = text[section_start:body_start]
        body = text[body_start:body_end]
        title = match.group(2).lower()
        if "general objective" in title:
            kind = "general_objective"
        elif "question" in title or "hypoth" in title:
            kind = "questions"
        else:
            kind = "objectives"
        parts.append(text[last:section_start])
        parts.append(heading)
        parts.append("\n" + _normalise_numbered_items_in_section(body.strip("\n"), kind) + "\n")
        last = tail_start
    parts.append(text[last:])
    result = "".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _normalise_purpose_of_study(text: str) -> str:
    """Keep Purpose of the Study concise while preserving a necessary action item."""
    if not text:
        return text
    heading_re = re.compile(
        r"(?im)^(#{1,4}\s*)?(?:\d+(?:\.\d+){0,3}\s+)?Purpose of the Study\s*$"
    )
    match = heading_re.search(text)
    if not match:
        return text

    body_start = match.end()
    next_heading = re.search(
        r"(?im)^\s*(?:#{1,4}\s+[^\n]{2,120}|\d+\.\d+(?:\.\d+)*\s+[A-Z][^\n]{2,120})$",
        text[body_start:],
    )
    body_end = body_start + next_heading.start() if next_heading else len(text)
    body = text[body_start:body_end].strip()
    if not body:
        return text

    actions = []
    prose_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^\[[^\]]+\]$", stripped):
            if stripped not in actions:
                actions.append(stripped)
        elif stripped:
            prose_lines.append(stripped)
    prose = re.sub(r"\s+", " ", " ".join(prose_lines)).strip()
    if not prose:
        return text

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if s.strip()]
    selected = ""
    for sentence in sentences[:3]:
        if re.search(r"\b(?:purpose|aim|sought|examine|assess|determine|investigate|explore|evaluate|analyse|analyze)\b", sentence, re.I):
            selected = sentence
            break
    selected = selected or (sentences[0] if sentences else prose)
    words = selected.split()
    if len(words) > 85:
        selected = " ".join(words[:85]).rstrip(",;:") + "."
    selected = selected.strip()

    replacement = [text[match.start():body_start].rstrip(), selected]
    if actions:
        replacement.extend(["", actions[0]])
    tail = text[body_end:]
    return (text[:match.start()] + "\n".join(replacement) + tail).strip()


def _reference_entries_from_text(reference_text: str) -> list[str]:
    """Extract, deduplicate and alphabetise clean reference paragraphs."""
    entries: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        entry = re.sub(r"\s+", " ", " ".join(current)).strip()
        current.clear()
        if entry:
            entries.append(entry)

    for raw_line in (reference_text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("|") or re.match(r"^#{1,6}\s+", stripped):
            continue
        cleaned = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", stripped).strip()
        if not cleaned:
            continue
        is_placeholder = bool(re.match(r"^\[[^\]]+\]$", cleaned))
        starts_entry = bool(
            re.search(r"\((?:19|20)\d{2}[a-z]?\)|\(n\.d\.\)", cleaned, re.I)
            and not re.match(r"^(?:https?://|doi\b)", cleaned, re.I)
        )
        if is_placeholder:
            flush()
            entries.append(cleaned)
        elif starts_entry:
            flush()
            current.append(cleaned)
        elif current:
            current.append(cleaned)
        else:
            current.append(cleaned)
    flush()

    unique: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        key = re.sub(r"[^a-z0-9]+", "", entry.lower())[:240]
        if key and key not in seen:
            seen.add(key)
            unique.append(entry)

    def sort_key(entry: str) -> tuple[int, str]:
        placeholder = 1 if entry.startswith("[") else 0
        normal = re.sub(r"^[^A-Za-z0-9]+", "", entry).lower()
        return placeholder, normal

    return sorted(unique, key=sort_key)


def _ensure_markdown_heading_spacing(text: str) -> str:
    """Ensure chapter headings are separated from the preceding paragraph or list."""
    value = str(text or "")
    value = re.sub(r"(?m)(?<!\n)\n(?=#{1,4}\s)", "\n\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _clean_chapter_references(text: str) -> str:
    """Return one clean References list and remove internal source-audit material."""
    if not text:
        return text
    match = re.search(
        r"(?im)^#{0,4}\s*(?:\d+(?:\.\d+)*\s+)?(?:References|Reference List)\s*$",
        text,
    )
    if not match:
        return text

    after = text[match.end():]
    audit = re.search(r"(?im)^#{0,4}\s*Source Use Audit\s*$", after)
    appendix = re.search(r"(?im)^#{0,4}\s*(?:Appendix|Appendices)\b.*$", after)
    cut_positions = [m.start() for m in (audit, appendix) if m]
    refs_end = min(cut_positions) if cut_positions else len(after)
    refs_text = after[:refs_end]

    appendix_tail = ""
    if appendix:
        appendix_tail = after[appendix.start():]
    entries = _reference_entries_from_text(refs_text)
    if not entries:
        entries = ["[Insert complete APA 7 reference entries for every source cited in the chapter body.]" ]

    cleaned_refs = "# References\n\n" + "\n\n".join(entries)
    result = text[:match.start()].rstrip() + "\n\n" + cleaned_refs
    if appendix_tail.strip():
        result += "\n\n" + appendix_tail.strip()
    return result.strip()


def _remove_stray_transition_prefixes(text: str) -> str:
    """Remove transition words that sometimes leak into table rows, item codes and scale points."""
    if not text:
        return text
    words = r"(?:Indeed|Conversely|Still|Yet|Importantly|Besides)"
    # Beginning of line before item codes, scale points, table text or equations
    text = re.sub(rf"(?m)^\s*{words},\s+(?=(?:[A-Z]{{2,5}}\d+|SQ\d+|OUT\d+|\d\b|[-*•]|\|))", "", text)
    # Beginning of ordinary lines where the transition is stranded as a prefix
    text = re.sub(rf"(?m)^\s*{words},\s*$\n", "", text)
    # Inside markdown table cells
    text = re.sub(rf"(\|\s*){words},\s+", r"\1", text)
    return text

def _finalise_output_controls(text: str) -> str:
    """Final pass applied to AI and fallback outputs."""
    text = _strip_colour_markup(text or "")
    text = _normalise_attention_language(text)
    text = _minimise_em_en_dashes(text)
    text = _remove_stray_transition_prefixes(text)
    text = _protect_thesis_structure(text)
    text = _normalise_purpose_of_study(text)
    text = _normalise_objectives_and_questions(text)
    text = _clean_chapter_references(text)
    text = _ensure_markdown_heading_spacing(text)
    text = _protect_thesis_structure(text)
    return text.strip()

# ----------------------------------------------------------------------
# SOURCE INTEGRATION AND OTHER HELPERS (unchanged from original)
# ----------------------------------------------------------------------

def _source_usage_count(text: str, sources: list[dict[str, Any]]) -> int:
    if not text or not sources:
        return 0
    body = text
    refs_match = re.search(r"(?im)^#{0,3}\s*references\b", text)
    if refs_match:
        body = text[: refs_match.start()]
    used = 0
    lower_body = body.lower()
    for src in sources:
        year = str(src.get("year") or "").strip()
        authors = src.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        family_names = [_normalise_author_for_citation(a).lower() for a in authors if str(a).strip()]
        family_names = [f for f in family_names if f and f != "[author]"]
        if not family_names:
            continue
        first = re.escape(family_names[0])
        year_ok = bool(year and year != "n.d." and re.search(re.escape(str(year)), body))
        author_ok = bool(re.search(first, lower_body))
        if author_ok and (year_ok or len(family_names) == 1):
            used += 1
    return used


def _source_reference_hints(sources: list[dict[str, Any]]) -> str:
    lines = []
    for src in sources:
        hint = src.get("apa_hint") or src.get("reference_entry_hint") or ""
        citation = _citation_label_for_source(src)
        title = src.get("title", "")
        if hint:
            lines.append(f"- {src.get('citation_key', '')} {citation}: {hint}")
        elif title:
            lines.append(f"- {src.get('citation_key', '')} {citation}: {title}")
    return "\n".join(lines)


def _has_source_use_audit(text: str) -> bool:
    return bool(re.search(r"(?im)^#{0,3}\s*source\s+use\s+audit\b", text or ""))


def _relevant_source_bank(profile: dict[str, Any]) -> list[dict[str, Any]]:
    sources = _merged_source_bank(profile)
    relevant = [s for s in sources if str(s.get("relevance_tier") or "").lower() in {"highly_relevant", "partly_relevant", "unclassified"}]
    relevant.sort(key=lambda item: _relevance_tier_rank(item.get("relevance_tier")), reverse=True)
    return relevant


def _review_source_integration(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    source_bank = _merged_source_bank(profile)
    if not source_bank:
        return draft

    relevant_sources = _relevant_source_bank(profile)
    used = _source_usage_count(draft, relevant_sources)
    has_audit = _has_source_use_audit(draft)
    length_requirements = _chapter_length_requirements(profile, chapter_number)

    if used > 0 and has_audit:
        return draft

    repair_payload = {
        "task": "Review the chapter draft against the attached source-search results using a relevance gate.",
        "chapter_number": chapter_number,
        "chapter_length_requirements": length_requirements,
        "reason_for_review": (
            f"The attached source search returned {len(source_bank)} source records. About {used} relevant source-bank records appear to be cited in the body. "
            "Revise only where relevant searched sources genuinely support the chapter. Do not force unsuitable sources into the prose."
        ),
        "important_rules": [
            "Keep the student's project profile, uploaded results, supplied references, and placeholders; do not replace them.",
            "Use highly_relevant and partly_relevant source-bank records where they directly support a specific point, theory, method, context, empirical gap, or discussion.",
            "Do not cite sources marked not_relevant unless the student's own notes explicitly confirm their relevance.",
            "Do not cite a source unless it supports the specific sentence or paragraph being written.",
            "If no searched source fits a claim, keep or add a bracketed placeholder instead of forcing a citation.",
            "Increase citation density only where doing so improves scholarly support and accuracy.",
            "End the chapter with a References section for sources actually cited in the body.",
            "Do not invent new sources, statistics, page numbers, quotations, findings, or reference details.",
            "Preserve or increase the chapter's substantive word count. Do not compress a developed chapter into a shorter summary during source integration.",
            "Keep the revised chapter within the stated minimum and maximum word range where the evidence bank permits it.",
        ],
        "source_bank_reference_hints": _source_reference_hints(source_bank),
        "original_generation_prompt": original_prompt,
        "draft_to_revise": draft,
    }
    revised = _call_openai_response_safely(
        client,
        model,
        instructions + " Revise rather than restart. Preserve the student's context and depth. Use only directly relevant attached sources and return one clean References section containing only cited sources.",
        json.dumps(repair_payload, ensure_ascii=False, indent=2),
        max_output_tokens=_max_output_tokens_for_length(length_requirements, revision=True),
    )
    if revised:
        return _polish_generated_text(revised)
    return draft


def _generic_language_score(text: str) -> int:
    patterns = [
        r"\bin today's world\b", r"\bit is important to note\b", r"\bdelve into\b",
        r"\bplays a crucial role\b", r"\bvarious factors\b", r"\bsignificant impact\b",
        r"\bthis highlights the importance\b", r"\bthis study aims to contribute\b",
        r"\bmoreover\b", r"\bfurthermore\b", r"\bthe research problem is that\b",
    ]
    lower = text or ""
    return sum(len(re.findall(pattern, lower, flags=re.IGNORECASE)) for pattern in patterns)


def _sentence_length_variance(text: str) -> float:
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) < 2:
        return 0.0
    lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return variance


def _humanizer_batch_token_budget(word_count: int) -> int:
    """Estimate a conservative output ceiling for a style-only batch."""
    words = max(250, int(word_count or 0))
    # Academic English averages roughly 1.3-1.7 tokens per word. The buffer allows
    # the model to preserve headings, citations and action lines without inviting expansion.
    return max(1800, min(9000, int(words * 2.1)))


def _refine_humanizer_batch_with_model(
    *,
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    batch_text: str,
    controls: dict[str, Any],
    chapter_number: int,
    diagnostic: dict[str, Any],
) -> str:
    payload = {
        "task": "Apply a high-variation scholarly naturalness edit to this chapter section without changing its evidence or argument.",
        "chapter_number": chapter_number,
        "variation_profile": humanizer_variation_profile(),
        "student_contribution_controls": controls,
        "style_diagnostic": diagnostic,
        "quality_rules": [
            "Revise the supplied section rather than rewriting it from scratch.",
            *scholarly_humanizer_prompt_rules(),
            "Preserve every heading, objective, research question, hypothesis, citation, reference, date, statistic, table, equation, quotation and bracketed action item exactly.",
            "Preserve the sequence of ideas and the strength of every claim. Do not add evidence, examples, citations, findings, recommendations or interpretations.",
            "Increase controlled perplexity through context-sensitive lexical and syntactic variety, not obscure vocabulary or random synonym replacement.",
            "Increase controlled burstiness through a purposeful mix of concise, medium and longer synthesis sentences, with paragraph lengths that reflect different argumentative functions.",
            "Improve naturalness through clearer subjects and verbs, varied but purposeful sentence movement, less repetitive framing, and transitions that match the logic.",
            "Do not make every paragraph the same length or end every paragraph with a summary sentence.",
            "Do not mechanically replace ordinary words with rare synonyms and do not remove discipline-specific terms.",
            "Keep the word count within six percent of the supplied section.",
            "Return only the complete revised section with its original headings. Do not add a report.",
        ],
        "original_generation_context": original_prompt,
        "section_to_refine": batch_text,
    }
    candidate = _call_openai_response_safely(
        client,
        model,
        instructions + " Perform one preservation-gated, high-variation scholarly naturalness edit. Return only the revised section.",
        json.dumps(payload, ensure_ascii=False, indent=2),
        max_output_tokens=_humanizer_batch_token_budget(int(diagnostic.get("word_count") or 0)),
    )
    if not candidate:
        return batch_text
    candidate = _polish_generated_text(candidate)
    candidate, _ = humanize_scholarly_text(candidate, mode="balanced")
    valid, _issues = validate_humanizer_preservation(
        batch_text,
        candidate,
        max_word_change_ratio=float(humanizer_variation_profile()["model_word_change_limit"]),
    )
    return candidate if valid else batch_text


def _human_academic_revision_pass(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    """Run selective, section-batched scholarly naturalness refinement.

    Light mode uses only the deterministic local pass. Balanced mode refines only
    weak batches, with a strict cap to control cost. Deep mode refines all eligible
    batches, still preserving citations, statistics, headings and action items.
    """
    controls = _student_contribution_requirements(profile)
    mode = _humanizer_mode(profile)
    local_draft, local_report = humanize_scholarly_text(draft, mode=mode)
    if mode in {"off", "light"} or not controls.get("human_revision_pass_requested", True):
        return local_draft

    has_style_context = any(str(controls.get(k) or "").strip() for k in [
        "preferred_style", "writing_sample", "phrases_to_avoid", "supervisor_comments"
    ])
    threshold = int(os.getenv("PROJECTREADY_HUMANIZER_MODEL_THRESHOLD", "97") or 97)
    current_score = int(local_report.get("score") or 0)
    variation_profile = humanizer_variation_profile()
    variation_ready = variation_targets_met(local_report, variation_profile)
    should_call_model = mode == "deep" or has_style_context or current_score < threshold or not variation_ready
    if not should_call_model:
        return local_draft

    batch_words = int(os.getenv("PROJECTREADY_HUMANIZER_BATCH_WORDS", "1800") or 1800)
    batches = build_humanizer_batches(local_draft, max_words=batch_words)
    if not batches:
        return local_draft

    balanced_cap = int(os.getenv("PROJECTREADY_HUMANIZER_MAX_BATCHES_BALANCED", "6") or 6)
    deep_cap = int(os.getenv("PROJECTREADY_HUMANIZER_MAX_BATCHES_DEEP", "16") or 16)
    eligible_indices = [
        index for index, batch in enumerate(batches)
        if not batch.get("protected")
        and int((batch.get("diagnostic") or {}).get("word_count") or 0) >= 120
        and (
            mode == "deep"
            or has_style_context
            or int((batch.get("diagnostic") or {}).get("score") or 100) < threshold
            or not variation_targets_met(batch.get("diagnostic") or {}, variation_profile)
        )
    ]
    if mode == "balanced":
        eligible_indices.sort(key=lambda index: int((batches[index].get("diagnostic") or {}).get("score") or 100))
        eligible_indices = eligible_indices[:max(1, balanced_cap)]
    else:
        eligible_indices = eligible_indices[:max(1, deep_cap)]

    if not eligible_indices:
        return local_draft

    revised_parts: list[str] = []
    selected = set(eligible_indices)
    for index, batch in enumerate(batches):
        batch_text = str(batch.get("text") or "")
        if index not in selected:
            revised_parts.append(batch_text)
            continue
        revised_parts.append(_refine_humanizer_batch_with_model(
            client=client,
            model=model,
            instructions=instructions,
            original_prompt=original_prompt,
            batch_text=batch_text,
            controls=controls,
            chapter_number=chapter_number,
            diagnostic=dict(batch.get("diagnostic") or {}),
        ))

    candidate = "\n\n".join(part.strip() for part in revised_parts if part.strip()).strip()
    valid, _issues = validate_humanizer_preservation(local_draft, candidate, max_word_change_ratio=0.045)
    return candidate if valid else local_draft


def _call_openai_response_safely(
    client: Any,
    model: str,
    instructions: str,
    prompt: str,
    *,
    max_output_tokens: int | None = None,
) -> str:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": prompt,
    }
    if max_output_tokens:
        request_kwargs["max_output_tokens"] = int(max_output_tokens)
    try:
        response = client.responses.create(**request_kwargs)
        return str(getattr(response, "output_text", "") or "").strip()
    except Exception:
        # Some model snapshots have lower per-response output limits. Retry once
        # with a conservative cap before moving to the configured fallback model.
        safe_retry_cap = int(os.getenv("OPENAI_SAFE_RETRY_MAX_OUTPUT_TOKENS", "12000") or 12000)
        if max_output_tokens and int(max_output_tokens) > safe_retry_cap:
            try:
                request_kwargs["max_output_tokens"] = safe_retry_cap
                response = client.responses.create(**request_kwargs)
                return str(getattr(response, "output_text", "") or "").strip()
            except Exception:
                pass
        fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", "").strip()
        if fallback_model and fallback_model != model:
            try:
                request_kwargs["model"] = fallback_model
                response = client.responses.create(**request_kwargs)
                return str(getattr(response, "output_text", "") or "").strip()
            except Exception:
                return ""
        return ""


def _source_is_used_in_body(text: str, src: dict[str, Any]) -> bool:
    """Return True when a source's author/year pattern appears in the chapter body."""
    body = text or ""
    refs_match = re.search(r"(?im)^#{0,3}\s*references\b", body)
    if refs_match:
        body = body[: refs_match.start()]
    lower_body = body.lower()
    year = str(src.get("year") or "").strip()
    authors = src.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    family_names = [_normalise_author_for_citation(a).lower() for a in authors if str(a).strip()]
    family_names = [f for f in family_names if f and f != "[author]"]
    if not family_names:
        return False
    author_ok = bool(re.search(re.escape(family_names[0]), lower_body))
    year_ok = bool(year and year != "n.d." and re.search(re.escape(year), body))
    return author_ok and (year_ok or len(family_names) == 1)


def _strip_chunk_wrappers(text: str) -> tuple[str, list[str]]:
    """Remove duplicate chapter wrappers and separate chunk reference entries."""
    text = (text or "").strip()
    refs: list[str] = []
    marker = re.search(
        r"(?im)^#{1,4}\s*(?:references\s+used\s+in\s+this\s+chunk|chunk\s+references|references)\s*$",
        text,
    )
    if marker:
        ref_text = text[marker.end():]
        text = text[:marker.start()].rstrip()
        audit = re.search(r"(?im)^#{1,4}\s*source\s+use\s+audit\b", ref_text)
        if audit:
            ref_text = ref_text[:audit.start()]
        for line in ref_text.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if cleaned and not cleaned.startswith("#") and len(cleaned) > 12:
                refs.append(cleaned)

    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^#{0,3}\s*chapter\s+\d+\s*$", stripped):
            continue
        if re.match(r"(?i)^#{0,3}\s*(?:introduction|literature review|research methods|methodology|results(?:/data analysis)?(?: and discussion)?|summary,? conclusions? and recommendations?)\s+chapter\s*$", stripped):
            continue
        kept.append(line)
    return "\n".join(kept).strip(), refs


def _dedupe_reference_entries(entries: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        cleaned = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", str(entry or "").strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and not cleaned.endswith((".", "?", "!", "]")):
            cleaned += "."
        key = re.sub(r"[^a-z0-9]+", "", cleaned.lower())[:220]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return sorted(
        unique,
        key=lambda item: (1 if item.startswith("[") else 0, re.sub(r"^[^A-Za-z0-9]+", "", item).lower()),
    )


def _local_source_references_and_audit(profile: dict[str, Any], body: str) -> tuple[list[str], str]:
    """Build clean reference hints for attached source-search records used in the body.

    The second return value is retained for compatibility but is always empty.
    Source-selection diagnostics belong in the internal report, not in the thesis chapter.
    """
    sources = _merged_source_bank(profile)
    if not sources:
        return [], ""
    refs: list[str] = []
    for src in sources:
        if not _source_is_used_in_body(body, src):
            continue
        hint = str(src.get("apa_hint") or src.get("reference_entry_hint") or "").strip()
        if hint:
            refs.append(hint)
    return _dedupe_reference_entries(refs), ""


def _group_sections_for_chunks(
    selected_sections: list[dict[str, Any]],
    section_budgets: dict[str, dict[str, int]],
    total_target_words: int,
) -> list[list[dict[str, Any]]]:
    """Group adjacent sections into a small number of manageable generation chunks."""
    if not selected_sections:
        return []
    chunk_target = max(1500, int(os.getenv("PROJECTREADY_CHUNK_TARGET_WORDS", "3000") or 3000))
    max_chunks = max(2, int(os.getenv("PROJECTREADY_MAX_CHAPTER_CHUNKS", "10") or 10))
    desired_chunks = max(1, min(max_chunks, len(selected_sections), (max(1, total_target_words) + chunk_target - 1) // chunk_target))
    if desired_chunks <= 1:
        return [selected_sections]

    target_per_chunk = total_target_words / desired_chunks
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_words = 0
    for idx, section in enumerate(selected_sections):
        sid = str(section.get("section_id") or "")
        budget = int((section_budgets.get(sid) or {}).get("target_words") or 500)
        remaining_sections = len(selected_sections) - idx
        remaining_chunks_after_closing = desired_chunks - len(chunks) - 1
        must_split_to_reach_count = current and remaining_sections == remaining_chunks_after_closing
        budget_split_allowed = current and current_words >= target_per_chunk and remaining_sections >= remaining_chunks_after_closing
        if current and (must_split_to_reach_count or budget_split_allowed):
            chunks.append(current)
            current = []
            current_words = 0
        current.append(section)
        current_words += budget
    if current:
        chunks.append(current)
    return chunks


def _long_chapter_plan_fallback(base_prompt: dict[str, Any], chunks: list[list[dict[str, Any]]], full_req: dict[str, Any]) -> str:
    """Create a compact local plan if the planning model is unavailable."""
    chapter = base_prompt.get("chapter") or {}
    lines = [
        f"Long-chapter development plan for Chapter {chapter.get('chapter_number')}: {chapter.get('chapter_title')}",
        f"Target range: {full_req.get('target_page_range')} pages, target words: {full_req.get('target_words')}",
        "Use each chunk as a development unit, then merge for coherence without compressing arguments.",
    ]
    strategy = (full_req.get("long_chapter_strategy") or {}).get("recommended_workflow") or []
    if strategy:
        lines.append("Recommended workflow units:")
        for item in strategy:
            if isinstance(item, dict):
                lines.append(f"- {item.get('unit')}: {item.get('purpose')}")
    lines.append("Chunk map:")
    for index, chunk in enumerate(chunks, start=1):
        names = "; ".join(str(section.get("section_title") or section.get("section_id")) for section in chunk)
        lines.append(f"- Chunk {index}: {names}")
    return "\n".join(lines)


def _build_long_chapter_plan(
    client: Any,
    model: str,
    instructions: str,
    base_prompt: dict[str, Any],
    full_req: dict[str, Any],
    chunks: list[list[dict[str, Any]]],
) -> str:
    """Ask the model for a compact plan before generating a very long chapter."""
    fallback = _long_chapter_plan_fallback(base_prompt, chunks, full_req)
    if not client:
        return fallback
    chapter = base_prompt.get("chapter") or {}
    plan_payload = {
        "task": "Prepare a compact chapter-development plan before drafting a very long academic chapter.",
        "chapter": chapter,
        "project_profile": base_prompt.get("project_profile") or {},
        "draft_grounding_and_provisional_mode": base_prompt.get("draft_grounding_and_provisional_mode") or {},
        "previous_chapters_for_alignment": base_prompt.get("previous_chapters_for_alignment") or {},
        "retrieved_sources": base_prompt.get("retrieved_sources") or {},
        "chapter_page_word_and_citation_targets": full_req,
        "selected_sections": base_prompt.get("selected_sections") or [],
        "chunk_map": [
            {
                "chunk_number": idx,
                "sections": [section.get("section_title") or section.get("section_id") for section in chunk],
            }
            for idx, chunk in enumerate(chunks, start=1)
        ],
        "plan_rules": [
            "Return a concise development plan, not the chapter itself.",
            "For Chapter Two doctoral literature reviews, include conceptual, theoretical, empirical, methodological, contextual, contradiction, gap and framework development logic.",
            "Indicate which objectives, constructs, theories, methods and context points each chunk should protect.",
            "State where missing student inputs should be marked with bracketed placeholders.",
            "Do not invent source details, facts, findings, statistics or institutional decisions.",
        ],
    }
    try:
        plan = _call_openai_response_safely(
            client,
            model,
            instructions + " Create the long-chapter plan only. Do not draft the chapter yet.",
            json.dumps(plan_payload, ensure_ascii=False, indent=2),
            max_output_tokens=6000,
        )
    except Exception:
        plan = ""
    return _polish_generated_text(plan).strip() if plan else fallback


def _generate_chapter_in_chunks(
    client: Any,
    model: str,
    instructions: str,
    prompt: str,
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
) -> str:
    """Generate long chapters in contiguous section chunks and assemble one chapter."""
    try:
        base_prompt = json.loads(prompt)
    except Exception:
        return ""

    full_req = _chapter_length_requirements(profile, chapter_number, selected_section_ids)
    selected_sections = list(base_prompt.get("selected_sections") or [])
    section_budgets = dict(full_req.get("section_word_budgets") or {})
    chunks = _group_sections_for_chunks(
        selected_sections,
        section_budgets,
        int(full_req.get("target_words") or 0),
    )
    if len(chunks) <= 1:
        return ""

    long_chapter_plan = _build_long_chapter_plan(
        client=client,
        model=model,
        instructions=instructions,
        base_prompt=base_prompt,
        full_req=full_req,
        chunks=chunks,
    )

    bodies: list[str] = []
    references: list[str] = []
    citation_density = full_req.get("citation_occurrences_per_1000_words") or {}

    for chunk_index, chunk_sections in enumerate(chunks, start=1):
        chunk_ids = [str(section.get("section_id") or "") for section in chunk_sections]
        chunk_target_words = sum(int((section_budgets.get(sid) or {}).get("target_words") or 500) for sid in chunk_ids)
        chunk_min_words = sum(int((section_budgets.get(sid) or {}).get("minimum_words") or 350) for sid in chunk_ids)
        chunk_max_words = max(chunk_target_words + 500, int(chunk_target_words * 1.18))
        chunk_req = {
            **full_req,
            "target_page_range": f"chunk {chunk_index} of {len(chunks)}",
            "minimum_words": chunk_min_words,
            "target_words": chunk_target_words,
            "maximum_words": chunk_max_words,
            "section_word_budgets": {sid: section_budgets.get(sid, {}) for sid in chunk_ids},
            "chunk_sequence": {"current": chunk_index, "total": len(chunks)},
        }
        chunk_prompt = dict(base_prompt)
        chunk_prompt["task"] = f"Develop contiguous section chunk {chunk_index} of {len(chunks)} for one coherent academic working draft."
        chunk_prompt["selected_sections"] = chunk_sections
        chunk_prompt["chapter_page_word_and_citation_targets"] = chunk_req
        chunk_prompt["long_chapter_development_plan"] = long_chapter_plan
        chunk_prompt["output_requirements"] = list(base_prompt.get("output_requirements") or []) + [
            "Return only the selected sections in this chunk, in their approved order, with their correct numbered headings.",
            "Do not repeat the overall chapter heading or sections assigned to another chunk.",
            "Use long_chapter_development_plan to keep the chunk connected to the full chapter argument, objectives, constructs, theories and gaps.",
            "Where a broad section is assigned a large word budget, subdivide it with meaningful lower-level headings such as conceptual dimensions, theoretical comparison, empirical clusters by objective, methodological patterns, contextual evidence, contradictions and gaps.",
            f"Develop this chunk to approximately {chunk_target_words:,} words and at least {chunk_min_words:,} words, subject to evidence availability.",
            f"Plan for about {citation_density.get('minimum', 3)}-{citation_density.get('target', 6)} accurate citation occurrences per 1,000 substantive words, without forcing irrelevant sources.",
            "At the end, add a heading exactly named '## References Used in This Chunk' and list complete APA 7 entries only for sources cited in this chunk.",
            "Do not add a Source Use Audit. The final chapter must end with the clean consolidated References list only.",
        ]
        chunk_text = _call_openai_response_safely(
            client,
            model,
            instructions + f" Produce chunk {chunk_index} of {len(chunks)} only. Maintain continuity with the overall chapter plan.",
            json.dumps(chunk_prompt, ensure_ascii=False, indent=2),
            max_output_tokens=_max_output_tokens_for_length(chunk_req),
        )
        if not chunk_text:
            return ""

        chunk_body, chunk_refs = _strip_chunk_wrappers(_polish_generated_text(chunk_text))
        current_chunk_words = _chapter_word_count(chunk_body)
        if current_chunk_words < int(chunk_min_words * 0.72):
            retry_payload = {
                "task": "Expand this chapter chunk without changing its assigned headings or inventing evidence.",
                "chunk_length_requirements": chunk_req,
                "rules": [
                    "Return the complete replacement chunk.",
                    "Preserve accurate content, citations, tables, equations, results and placeholders.",
                    "Add depth through synthesis, critique, explanation, interpretation and context-specific application.",
                    "Do not repeat content or add unsupported facts.",
                    "End with '## References Used in This Chunk'.",
                ],
                "chunk_to_expand": chunk_text,
            }
            retry = _call_openai_response_safely(
                client,
                model,
                instructions + " Expand the assigned chunk to its minimum depth while preserving evidence integrity.",
                json.dumps(retry_payload, ensure_ascii=False, indent=2),
                max_output_tokens=_max_output_tokens_for_length(chunk_req, revision=True),
            )
            if retry:
                retry_body, retry_refs = _strip_chunk_wrappers(_polish_generated_text(retry))
                if _chapter_word_count(retry_body) > current_chunk_words:
                    chunk_body, chunk_refs = retry_body, retry_refs

        chunk_body, _chunk_humanizer_report = humanize_scholarly_text(
            chunk_body,
            mode=_humanizer_mode(profile),
        )
        bodies.append(chunk_body)
        references.extend(chunk_refs)

    chapter = get_chapter(chapter_number)
    chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    body = "\n\n".join(part for part in bodies if part.strip()).strip()
    source_refs, _unused_audit = _local_source_references_and_audit(profile, body)
    references = _dedupe_reference_entries([*references, *source_refs])

    output = [f"# CHAPTER {chapter_number}", f"# {chapter_title.upper()}", "", body]
    if references:
        output.extend(["", "# References", "", *references])
    else:
        output.extend(["", "# References", "", "[Insert complete APA 7 reference entries for every source cited in the chapter body.]" ])
    return _clean_chapter_references("\n".join(output).strip())


def _ensure_chapter_depth(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
) -> str:
    """Run one evidence-safe expansion pass when a generated chapter is materially short."""
    requirements = _chapter_length_requirements(profile, chapter_number, selected_section_ids)
    minimum_words = int(requirements.get("minimum_words") or 0)
    current_words = _chapter_word_count(draft)
    threshold = int(minimum_words * float(os.getenv("PROJECTREADY_DEPTH_ACCEPTANCE_RATIO", "0.90") or 0.90))
    if minimum_words <= 0 or current_words >= threshold:
        return draft

    expansion_payload = {
        "task": "Expand the existing chapter into a complete replacement chapter that reaches the required academic depth without inventing evidence.",
        "chapter_number": chapter_number,
        "current_word_count": current_words,
        "chapter_length_requirements": requirements,
        "selected_section_ids": selected_section_ids,
        "expansion_rules": [
            "Return the complete revised chapter, not comments, an outline, or isolated add-on paragraphs.",
            "Preserve all accurate existing content, headings, citations, tables, equations, supplied results and bracketed attention placeholders.",
            "Expand underdeveloped selected sections according to section_word_budgets.",
            "Create depth through critical synthesis, comparisons, theoretical reasoning, methodological justification, interpretation, contextual application and objective alignment.",
            "Do not repeat the same definition, claim, evidence or conclusion merely to increase length.",
            "Increase citation density using only relevant sources already present in the project profile, retrieved source bank, uploaded material or verified user notes.",
            "Where adequate evidence is missing, insert a precise bracketed source or evidence placeholder rather than fabricating content.",
            "For Chapter Four, never invent results. Expand interpretation and discussion only from supplied results, and use placeholders for missing outputs.",
            "Retain one consolidated, clean and alphabetised References section containing only sources cited in the chapter body. Do not add a Source Use Audit to the chapter.",
            "Aim for at least the minimum word count and do not exceed the maximum word count.",
        ],
        "original_generation_prompt": original_prompt,
        "existing_chapter_to_expand": draft,
    }
    expanded = _call_openai_response_safely(
        client,
        model,
        instructions + " Expand for academic depth without padding, repetition or invented evidence. Preserve the complete chapter structure.",
        json.dumps(expansion_payload, ensure_ascii=False, indent=2),
        max_output_tokens=_max_output_tokens_for_length(requirements, revision=True),
    )
    if not expanded:
        return draft

    expanded = _polish_generated_text(expanded)
    expanded_words = _chapter_word_count(expanded)
    # Use the replacement only when it is genuinely fuller and structurally useful.
    if expanded_words >= max(int(current_words * 1.10), int(minimum_words * 0.75)):
        return expanded
    return draft


def _citation_occurrence_count(text: str) -> int:
    """Estimate author-year and numeric in-text citation occurrences in the chapter body."""
    text = text or ""
    reference_heading = re.search(r"(?im)^#{0,4}\s*references\s*$", text)
    if reference_heading:
        text = text[: reference_heading.start()]
    author_year = re.findall(
        r"(?:\([A-Z][A-Za-z’'\-]+(?:\s+(?:&|and)\s+[A-Z][A-Za-z’'\-]+|\s+et\s+al\.)?,?\s*(?:19|20)\d{2}[a-z]?[^)]*\)|"
        r"\b[A-Z][A-Za-z’'\-]+(?:\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\))",
        text,
    )
    numeric = re.findall(r"(?<!\w)(?:\[(?:\d+\s*[-,;]?\s*)+\]|\((?:\d+\s*[-,;]?\s*)+\))", text)
    return len(author_year) + len(numeric)


def chapter_output_metrics(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    text: str,
) -> dict[str, Any]:
    """Return transparent length and citation estimates for the workspace response."""
    requirements = _chapter_length_requirements(profile, chapter_number, selected_section_ids)
    words = _chapter_word_count(text)
    estimated_pages = round(words / WORDS_PER_PAGE_ESTIMATE, 1) if words else 0.0
    citations = _citation_occurrence_count(text)
    per_1000 = round(citations * 1000 / words, 1) if words else 0.0
    return {
        "word_count": words,
        "estimated_pages": estimated_pages,
        "citation_occurrences": citations,
        "citation_occurrences_per_1000_words": per_1000,
        "target_page_range": requirements.get("target_page_range"),
        "minimum_words": requirements.get("minimum_words"),
        "target_words": requirements.get("target_words"),
        "maximum_words": requirements.get("maximum_words"),
        "depth_target_reached": words >= int((requirements.get("minimum_words") or 0) * 0.90),
    }


# ----------------------------------------------------------------------
# MAIN GENERATION FUNCTION
# ----------------------------------------------------------------------

def generate_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    use_ai: bool = True,
) -> tuple[str, str]:
    """
    Generate a chapter using OpenAI (if available) or fallback to local templates.
    Incorporates a protected scholarly humanizer and evidence-preserving quality passes.
    """
    try:
        prompt = build_drafting_prompt(profile, chapter_number, selected_section_ids, answers, extra_instructions)
    except Exception:
        return (
            detach_action_items(_finalise_output_controls(_polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)))),
            "local_template_fallback_prompt_error"
        )

    client = _safe_get_openai_client()
    length_requirements = _chapter_length_requirements(profile, chapter_number, selected_section_ids)
    if use_ai and client:
        model, model_route = _select_draft_model(profile, chapter_number)
        revision_model = _select_revision_model(profile, chapter_number, model)
        instructions = (
            "You are ProjectReady AI, an academic project-work drafting and compliance assistant. "
            "Write in a natural, high-standard scholarly voice that sounds like a carefully supervised draft, "
            "built from the student's own evidence, context, supervisor comments and project decisions. "
            "Apply a protected scholarly-humanizer standard: vary sentence and paragraph rhythm where the argument requires it, "
            "use context-specific transitions, and prefer clear disciplinary vocabulary over rare synonyms. "
            "Never mention the selected academic level, template, or checklist. Avoid generic AI phrasing, filler, overclaiming, "
            "and perfectly balanced paragraphs. Use grounded verbs (suggests, indicates, complicates, qualifies). "
            "Do not begin problem statements with 'The research problem is that'. Frame problems through evidence, tension, or gap. "
            "Do not fabricate sources, results, approvals, or evidence. Use clear [bracketed placeholders] when information is missing. "
            "Write as a completed final project (past tense for methodology, future only for suggested research in Ch5). "
            "For Ch2: use clean markdown gap tables and Mermaid flowcharts for diagrams. For equations: display blocks with $$. "
            "For Ch4: never invent output; present only supplied results. Apply reference currency (≥70% recent, but allow older where needed). "
            "Include accurate in-text citations. For source-finder results: integrate only highly_relevant/partly_relevant records, "
            "exclude not_relevant, and end with one clean alphabetised References list containing only cited sources. Do not add a Source Use Audit, AI-detection note or humanisation note. "
            "For the Supplementary Methods and Analysis Guide, use sample outputs only as structural guides, not as content templates. "
            "Do not hard-code sample topics, sources, constructs, item wording or contexts. Use only the current project profile and source bank. "
            "Apply the level-based quality route: Bachelor outputs must still be complete paid thesis drafts; non-research Masters outputs must be stronger and professionally applied; Research Masters/MPhil outputs must show deeper research synthesis; PhD/DBA/doctoral outputs must show advanced critique, defensible contribution and doctoral-level scholarly judgement. "
            "Just produce normal scholarly prose."
        )

        chunk_threshold = int(os.getenv("PROJECTREADY_CHUNKED_GENERATION_THRESHOLD_WORDS", "4500") or 4500)
        chunked_generation = (
            int(chapter_number or 0) in {1, 2, 3, 4, 5}
            and int(length_requirements.get("target_words") or 0) > chunk_threshold
        )
        if chunked_generation:
            text = _generate_chapter_in_chunks(
                client=client,
                model=model,
                instructions=instructions,
                prompt=prompt,
                profile=profile,
                chapter_number=chapter_number,
                selected_section_ids=selected_section_ids,
            )
        else:
            text = _call_openai_response_safely(
                client,
                model,
                instructions,
                prompt,
                max_output_tokens=_max_output_tokens_for_length(length_requirements),
            )
        if text:
            # 1. Basic polish
            polished = _polish_generated_text(text)

            # 2. Remove legacy humanizer artefacts before evidence and depth passes.
            polished, _ = humanize_scholarly_text(polished, mode="light")

            if not chunked_generation:
                # 3. Relevance-gated source integration
                polished = _review_source_integration(
                    client=client,
                    model=model,
                    instructions=instructions,
                    original_prompt=prompt,
                    draft=polished,
                    profile=profile,
                    chapter_number=chapter_number,
                )

            # 4. Enforce the page/word depth target before the final naturalness pass.
            # This ensures any added depth receives the same protected style refinement.
            polished = _ensure_chapter_depth(
                client=client,
                model=revision_model,
                instructions=instructions,
                original_prompt=prompt,
                draft=polished,
                profile=profile,
                chapter_number=chapter_number,
                selected_section_ids=selected_section_ids,
            )

            # 5. Refine weak sections in controlled batches. Long chapters are no longer
            # skipped or rewritten as one block, which protects depth and controls cost.
            humanizer_model = os.getenv("OPENAI_HUMANIZER_MODEL", "gpt-5.6-terra").strip() or revision_model
            polished = _human_academic_revision_pass(
                client=client,
                model=humanizer_model,
                instructions=instructions,
                original_prompt=prompt,
                draft=polished,
                profile=profile,
                chapter_number=chapter_number,
            )

            # 6. Apply the protected deterministic humanizer once, after content,
            #    evidence and depth are settled. This pass preserves citations,
            #    numbers, headings, tables, equations and attention placeholders.
            polished, _humanizer_report = humanize_scholarly_text(
                polished,
                mode=_humanizer_mode(profile),
            )
            polished = _cluster_citations(polished)

            # 7. Final output controls for structure, dashes, attention placeholders and table noise.
            polished = _finalise_output_controls(polished)
            polished = detach_action_items(polished)

            generation_mode = "chunked_depth" if chunked_generation else "single_pass_depth"
            return polished, f"openai_responses_api:{model_route}:{model}:{generation_mode}"

    # Fallback when AI is disabled or fails
    return (
        _finalise_output_controls(_polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers))),
        "local_template_fallback"
    )


# ----------------------------------------------------------------------
# FALLBACK CHAPTER GENERATION (unchanged from original)
# ----------------------------------------------------------------------

def generate_fallback_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
) -> str:
    chapter = get_chapter(chapter_number)
    effective_chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}

    title = profile.get("title", "[Project Title]")
    lines = [
        f"# CHAPTER {chapter_number}",
        f"# {effective_chapter_title.upper()}",
        "",
        f"Study title: {title}",
        "",
    ]

    for index, section in enumerate(sections, 1):
        section_title = section["section_title"]
        section_answers = answers.get(section["section_id"], {})
        lines.append(f"## {chapter_number}.{index} {section_title}")
        lines.append("")
        if section["section_id"] == "ch2_gap_table":
            lines.append(_fallback_literature_gap_table(section_answers, profile))
        elif chapter_number == 4 and section["section_id"] in {"ch4_uploaded_results", "ch4_results_objectives"}:
            lines.append(_fallback_results_section(section_answers, profile, chapter_number))
        elif section_answers:
            lines.append(_draft_from_answers(section_title, section.get("rules", []), section_answers, profile, chapter_number))
        else:
            lines.append(_placeholder_paragraph(section_title, section.get("rules", []), profile, chapter_number))
        lines.append("")
    return "\n".join(lines).strip()


def _draft_from_answers(
    section_title: str,
    rules: list[str],
    section_answers: dict[str, Any],
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    joined_answers = []
    for key, value in section_answers.items():
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if str(v).strip())
        if str(value).strip():
            joined_answers.append(f"{key}: {value}")
    answer_text = " ".join(joined_answers)
    if not answer_text:
        return _placeholder_paragraph(section_title, rules, profile, chapter_number)

    rules_text = " ".join(rules[:3])
    if chapter_number == 3:
        return (
            f"The methodological choices in this section were shaped by the following study details: {answer_text}. "
            f"The section should be refined into a fully evidenced account of the procedures actually used, including dates, instruments, approvals, and verified methodological citations where required. "
            f"The discussion should remain aligned with these expectations: {rules_text}."
        )

    return (
        f"The section should be developed from the following study details: {answer_text}. "
        f"The discussion should connect these details to the study problem, objectives, context, and evidence base, while addressing these expectations: {rules_text}. "
        f"Where a claim requires support, insert accurate in-text citations, verified recent evidence, or relevant statistics rather than unsupported assertions."
    )


def _placeholder_paragraph(section_title: str, rules: list[str], profile: dict[str, Any], chapter_number: int) -> str:
    title = profile.get("title", "the study")
    requirements = " ".join(rules[:4]) if rules else "Follow the selected institutional requirements."

    if chapter_number == 3:
        return (
            f"This section requires the project-specific methodological details that were actually used in {title}. "
            f"The account should remain in past tense and should cover these methodological expectations: {requirements} "
            f"[insert study-specific methods, approvals, evidence, and citations here]."
        )

    return (
        f"This section requires further project-specific detail for {title}. "
        f"The discussion should be evidence-led and should address these expectations: {requirements} "
        f"[provide study-specific details, accurate evidence, statistics where relevant, and verified in-text citations here]."
    )


def _fallback_literature_gap_table(section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    objectives = profile.get("objectives") or profile.get("specific_objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    if not objectives:
        objectives = ["[insert research objective 1]", "[insert research objective 2]"]

    rows = [
        "| Research Objective | Key Authors and Year | Context of Study | Method Used | Key Findings | Identified Gap | Relevance to Current Study |",
        "|---|---|---|---|---|---|---|",
    ]
    for objective in objectives:
        rows.append(
            f"| {objective} | [insert author and year] | [insert study context] | [insert method] | [insert key finding] | [insert objective-specific gap] | [explain relevance to the present study] |"
        )
    return "\n".join(rows)


def _fallback_results_section(section_answers: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    uploaded = _uploaded_results_for_chapter(profile, chapter_number)
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    if not objectives:
        objectives = ["[insert research objective 1]", "[insert research objective 2]"]

    lines: list[str] = []
    extracted = str((uploaded or {}).get("extracted_text") or (uploaded or {}).get("preview") or "").strip()
    if extracted:
        lines.append(
            "The chapter should convert the supplied analysis evidence into clean academic results tables and interpretation. "
            "Do not mention the file upload in the final prose; present the evidence as normal thesis results."
        )
        lines.append("\n**Available analysis evidence for drafting use only:**\n")
        lines.append(extracted[:2200])
    else:
        lines.append(
            "The results required for this section were not supplied. The chapter should contain placeholder tables with bracketed attention placeholders and should tell the user exactly which analysis output is needed."
        )

    lines.append("\n**Objective-to-results table:**\n")
    lines.append("| Research Objective | Required Analysis/Table | Result to Report | Interpretation | Required Action if Missing |")
    lines.append("|---|---|---|---|---|")
    for objective in objectives:
        lines.append(
            f"| {objective} | [insert analysis method aligned with methodology] | [insert statistic/coefficient/theme/result] | [insert interpretation linked to objective] | [obtain the exact software/output table needed for this objective] |"
        )

    lines.append("\n**Suggested missing-results placeholders:**\n")
    lines.append("| Required Table/Figure | Purpose | Placeholder | User Action |")
    lines.append("|---|---|---|---|")
    lines.append("| Response rate or data profile | Establish final sample/dataset | [insert final sample, usable responses, response rate or dataset period] | Provide response summary or dataset description |")
    lines.append("| Descriptive statistics | Summarise variables/constructs | [insert means, standard deviations, frequencies or theme counts] | Provide descriptive output |")
    lines.append("| Main analysis table | Answer objectives/hypotheses | [insert coefficients, p-values, path estimates, themes or comparison statistics] | Provide regression/SEM/econometric/qualitative output |")
    lines.append("| Figure or diagram | Visualise key results/model | [insert Figure: results chart/path diagram/conceptual model here] | Provide chart, model output or diagram data |")

    lines.append("\n**Appendix guidance:** raw software output, long diagnostic tables, full questionnaires, interview transcripts, full correlation matrices, detailed coding sheets and robustness checks should normally go to the appendix unless a supervisor requires them in the main text.")

    if section_answers:
        joined = []
        for key, value in section_answers.items():
            if str(value).strip():
                joined.append(f"{key}: {value}")
        if joined:
            lines.append("\n**Student guidance supplied:** " + " ".join(joined))

    return "\n\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return blocks