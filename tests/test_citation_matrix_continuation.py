from pathlib import Path

from app.chapter_continuation import build_chapter_linkage, chapter_selection_is_complete
from app.citation_matrix import (
    CITATION_DENSITY_MATRIX,
    citation_target,
    reference_mention_count,
    remove_unverified_generated_citations,
)
from app.provisional_statistics import discover_provisional_statistics


def test_citation_matrix_matches_approved_ranges():
    assert CITATION_DENSITY_MATRIX["stem"] == {
        "introduction": (5, 10), "literature_review": (15, 25), "methodology": (2, 5),
        "results_discussion": (8, 15), "conclusion": (0, 3),
    }
    assert CITATION_DENSITY_MATRIX["social_sciences"]["literature_review"] == (20, 35)
    assert CITATION_DENSITY_MATRIX["humanities"]["results_discussion"] == (15, 25)
    assert CITATION_DENSITY_MATRIX["professional_health"]["methodology"] == (5, 10)


def test_business_auto_maps_to_professional_health_matrix():
    target = citation_target({"programme": "MBA Business Administration"}, 2)
    assert target["discipline_key"] == "professional_health"
    assert (target["minimum"], target["maximum"]) == (20, 30)


def test_grouped_citations_count_individual_referenced_works():
    text = "Evidence is mixed (Adams, 2024; Mensah, 2025; Boateng, 2026)."
    assert reference_mention_count(text) == 3


def test_unverified_generated_citation_and_reference_are_removed_fail_closed():
    profile = {
        "source_bank": [{
            "authors": ["Ama Mensah"], "year": 2025, "title": "Verified evidence",
            "doi": "10.1000/verified", "apa_hint": "Mensah, A. (2025). Verified evidence. Journal. https://doi.org/10.1000/verified",
        }]
    }
    text = """# Literature Review

Verified evidence exists (Mensah, 2025), but another claim cites a fabricated source (Fake, 2026).

# References

Fake, X. (2026). Invented article. Imaginary Journal.

Mensah, A. (2025). Verified evidence. Journal.
"""
    guarded, audit = remove_unverified_generated_citations(text, profile)
    assert "(Fake, 2026)" not in guarded
    assert "Invented article" not in guarded
    assert "insert verified source" in guarded
    assert "https://doi.org/10.1000/verified" in guarded
    assert audit["removed_unverified_count"] == 1
    assert audit["reference_list_policy"].startswith("Model-created references are discarded")


def test_provisional_statistics_come_only_from_source_text_with_locator():
    profile = {
        "source_bank": [
            {
                "authors": ["Ama Mensah"], "year": 2025, "title": "Employment survey",
                "doi": "10.1000/survey",
                "abstract": "The survey found that 63% of 420 respondents used digital payment services in the previous year.",
            },
            {
                "authors": ["Kojo Fake"], "year": 2025, "title": "Metadata only",
                "abstract": "This paper discusses adoption without reporting a numeric result.",
            },
        ]
    }
    candidates = discover_provisional_statistics(profile)
    assert len(candidates) == 1
    assert "63%" in candidates[0]["statement"]
    assert candidates[0]["source_locator"] == "https://doi.org/10.1000/survey"
    assert candidates[0]["status"] == "pending"


def test_chapter_one_completion_builds_linked_chapter_two_transition():
    profile = {
        "title": "Digital procurement and transparency",
        "programme": "MPhil Procurement",
        "expected_chapters": 5,
        "objectives": ["Examine the effect of digital procurement on transparency"],
        "research_questions": ["How does digital procurement affect transparency?"],
        "hypotheses": ["H1: Digital procurement positively affects transparency"],
        "variables": {"raw_variables": ["Digital procurement", "Transparency"]},
        "study_context": "Public institutions in Ghana",
        "source_bank": [],
    }
    linkage = build_chapter_linkage(profile, 1, draft_version={"id": "v1"})
    assert linkage["available"] is True
    assert linkage["next_chapter"] == 2
    assert linkage["objectives"] == profile["objectives"]
    assert linkage["research_questions"] == profile["research_questions"]
    assert "Chapter 1 has been saved as alignment context for Chapter 2" in linkage["automatic_alignment"]


def test_workspace_exposes_continuation_confirmation_and_citation_matrix():
    html = Path("app/static/workspace.html").read_text(encoding="utf-8")
    assert 'id="continueNextChapterBtn"' in html
    assert 'id="continuationCorrectionDetails"' in html
    assert 'id="provisionalStatisticsPanel"' in html
    assert 'id="citationDisciplineMatrix"' in html
    assert "20–35" in html


def test_strengthener_exposes_same_citation_matrix_safeguard():
    html = Path("app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    assert "Citation-density standard" in html
    assert "never fabricates an author, year, DOI, source, statistic or finding" in html


def test_next_chapter_prompt_requires_complete_standard_chapter_selection():
    from app.template_store import selected_sections
    all_ids = [section["section_id"] for section in selected_sections(1, [])]
    assert chapter_selection_is_complete(1, all_ids) is True
    assert chapter_selection_is_complete(1, all_ids[:3]) is False
