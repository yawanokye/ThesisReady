from pathlib import Path

import pytest

from app.chapter_revision_service import chapter_planning_targets, revise_chapter

ROOT = Path(__file__).resolve().parents[1]


def test_strengthener_ui_has_section_scope_and_page_controls():
    html = (ROOT / "app/static/chapter_strengthener.html").read_text()
    js = (ROOT / "app/static/chapter_strengthener.js").read_text()
    for identifier in [
        'id="uploadedContentScope"',
        'id="strengtheningScope"',
        'id="strengthenerSectionsBox"',
        'id="customNewSectionTitle"',
        'id="customTargetPagesEnabled"',
        'id="targetPageMin"',
        'id="targetPageMax"',
    ]:
        assert identifier in html
    assert "selected_section_titles" in js
    assert "new_section_titles" in js
    assert "custom_new_sections" in js


def test_custom_target_pages_override_default():
    target = chapter_planning_targets(
        "PhD",
        "2. Literature Review",
        custom_target_pages_enabled=True,
        target_page_min=72,
        target_page_max=88,
    )
    assert target["page_range"] == {"minimum": 72, "maximum": 88}
    assert target["custom_target_applied"] is True


def test_selected_section_target_is_proportional():
    target = chapter_planning_targets(
        "Research Masters / MPhil",
        "2. Literature Review",
        strengthening_scope="selected_sections",
        selected_section_count=2,
    )
    assert target["page_range"] == {"minimum": 8, "maximum": 14}


def test_complete_thesis_is_scoped_to_selected_chapter(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    full = """CHAPTER ONE\nINTRODUCTION\n\nThis is the introduction chapter with adequate content for testing. """ + ("Background text. " * 20) + """\n\nCHAPTER TWO\nLITERATURE REVIEW\n\nThis is the literature review chapter selected for strengthening. """ + ("Literature evidence and synthesis. " * 30) + """\n\nCHAPTER THREE\nMETHODOLOGY\n\nThis is the methodology chapter and must not be returned. """ + ("Method details. " * 20)
    result = revise_chapter({
        "thesis_title": "Test thesis",
        "chapter_type": "2. Literature Review",
        "chapter_text": full,
        "uploaded_content_scope": "complete_thesis",
        "academic_level": "Bachelors",
        "include_source_search": False,
    })
    assert result["scope_metadata"]["chapter_isolated"] is True
    assert "CHAPTER TWO" in result["processed_original_chapter_text"]
    assert "CHAPTER THREE" not in result["processed_original_chapter_text"]
    assert "CHAPTER ONE" not in result["processed_original_chapter_text"]


def test_selected_sections_require_a_selection(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Select at least one section"):
        revise_chapter({
            "thesis_title": "Test thesis",
            "chapter_type": "1. Introduction",
            "chapter_text": "CHAPTER ONE\n\n" + ("Substantive chapter text. " * 20),
            "strengthening_scope": "selected_sections",
            "academic_level": "Bachelors",
            "include_source_search": False,
        })
