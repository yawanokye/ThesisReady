import json

from app.ai_service import (
    CHAPTER_PAGE_TARGETS,
    _chapter_length_requirements,
    _group_sections_for_chunks,
    build_drafting_prompt,
    chapter_output_metrics,
)
from app.template_store import get_chapter, selected_sections


LEVEL_KEYS = {
    "Bachelors": "bachelors",
    "Non-Research Masters": "nonresearch_masters",
    "Research Masters (e.g. MPhil)": "research_masters",
    "Professional Doctorate (e.g. DBA, DEd)": "professional_doctorate",
    "PhD": "phd",
}


def _profile(level: str) -> dict:
    return {
        "title": "Digital Financial Literacy and Retirement Planning",
        "level": level,
        "research_area": "financial literacy",
        "study_context": "informal workers in Ghana",
        "objectives": ["Examine the relationship between financial literacy and retirement planning"],
    }


def test_page_targets_match_approved_matrix():
    expected = {
        "bachelors": {1: (10, 15), 2: (15, 22), 3: (10, 15), 4: (20, 25), 5: (8, 12)},
        "nonresearch_masters": {1: (10, 15), 2: (20, 30), 3: (12, 18), 4: (20, 30), 5: (8, 15)},
        "research_masters": {1: (15, 20), 2: (35, 45), 3: (15, 22), 4: (20, 32), 5: (8, 12)},
        "professional_doctorate": {1: (15, 22), 2: (40, 60), 3: (25, 35), 4: (35, 45), 5: (10, 15)},
        "phd": {1: (25, 35), 2: (60, 80), 3: (30, 45), 4: (60, 80), 5: (20, 30)},
    }
    assert CHAPTER_PAGE_TARGETS == expected


def test_prompt_contains_page_word_section_and_citation_targets():
    chapter = get_chapter(2)
    section_ids = [s["section_id"] for s in selected_sections(2, [])]
    prompt = json.loads(build_drafting_prompt(_profile("PhD"), 2, section_ids))
    targets = prompt["chapter_page_word_and_citation_targets"]

    assert targets["target_page_range"] == "60-80"
    assert targets["minimum_words"] == 60 * 330
    assert targets["maximum_words"] == 80 * 330
    assert targets["citation_occurrences_per_1000_words"] == {"minimum": 20, "target": 26}
    assert targets["section_word_budgets"]
    assert targets["long_chapter_strategy"]["enabled"] is True
    assert targets["long_chapter_strategy"]["mode"] == "long_chapter_staged_development"
    assert prompt["draft_grounding_and_provisional_mode"]
    assert prompt["selected_sections"]
    assert chapter["chapter_number"] == 2


def test_long_phd_chapter_is_split_into_contiguous_chunks():
    sections = selected_sections(2, [])
    ids = [s["section_id"] for s in sections]
    requirements = _chapter_length_requirements(_profile("PhD"), 2, ids)
    chunks = _group_sections_for_chunks(
        sections,
        requirements["section_word_budgets"],
        requirements["target_words"],
    )
    flattened = [s["section_id"] for chunk in chunks for s in chunk]

    assert 2 <= len(chunks) <= 10
    assert flattened == ids


def test_generation_metrics_report_estimated_pages_and_target_status():
    text = "word " * (10 * 330)
    metrics = chapter_output_metrics(_profile("Bachelors"), 1, ["ch1_background"], text)

    assert metrics["estimated_pages"] == 10.0
    assert metrics["target_page_range"] == "10-15"
    assert metrics["depth_target_reached"] is True

def test_nonresearch_masters_keeps_its_own_page_band():
    requirements = _chapter_length_requirements(_profile("Non-Research Masters"), 2, ["ch2_intro", "ch2_empirical_objectives"])
    assert requirements["length_level"] == "nonresearch_masters"
    assert requirements["target_page_range"] == "20-30"



def test_chapter_one_institutional_format_controls_are_in_prompt():
    profile = _profile("Bachelors")
    profile.update({
        "background_structure": "continuous_narrative",
        "purpose_statement_style": "concise_general_objective",
        "expected_chapters": 5,
    })
    prompt = json.loads(build_drafting_prompt(profile, 1, ["ch1_background", "ch1_purpose", "ch1_structure"]))
    controls = prompt["institutional_format_requirements"]
    assert controls["background_structure"] == "continuous_narrative"
    assert controls["purpose_statement_style"] == "concise_general_objective"
    assert controls["expected_chapters"] == 5
    assert any("Do not create numbered or titled subdimensions" in rule for rule in controls["background_rules"])
    assert any("one concise sentence" in rule for rule in controls["purpose_rules"])


def test_bachelors_chapter_one_uses_stronger_citation_target():
    req = _chapter_length_requirements(_profile("Bachelors"), 1, ["ch1_background", "ch1_problem"])
    assert req["citation_occurrences_per_1000_words"] == {"minimum": 8, "target": 10}
