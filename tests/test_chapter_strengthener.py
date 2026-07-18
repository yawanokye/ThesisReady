from app.chapter_revision_service import (
    chapter_planning_targets,
    export_revised_chapter_docx,
    revise_chapter,
)


def test_fallback_preserves_existing_chapter(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    original = "# Chapter One\n\nThis chapter introduces the study. " * 8
    result = revise_chapter({
        "thesis_title": "Digital procurement and public expenditure",
        "chapter_type": "1. Introduction",
        "chapter_text": original,
        "academic_level": "Research Masters / MPhil",
        "include_source_search": False,
    })
    assert result["revised_chapter_text"] == original.strip()
    assert result["mode"] == "metadata_fallback"
    assert result["target_page_range"] == "15-20"


def test_planning_targets_follow_level_and_chapter():
    target = chapter_planning_targets("PhD", "2. Literature Review")
    assert target["page_range"] == {"minimum": 60, "maximum": 80}
    assert target["citation_density_per_1000_words"] == {"minimum": 24, "maximum": 32}


def test_retracted_attached_source_is_excluded(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = revise_chapter({
        "thesis_title": "Governance and procurement",
        "chapter_type": "2. Literature Review",
        "chapter_text": "## Literature Review\n\nExisting literature discusses governance and procurement outcomes. " * 8,
        "academic_level": "Bachelors",
        "include_source_search": False,
        "source_bank": [
            {"title": "Governance and procurement outcomes", "year": 2025},
            {"title": "Retracted: Procurement governance", "is_retracted": True},
        ],
    })
    assert result["source_bank_count"] == 1
    assert result["excluded_retracted_count"] == 1


def test_docx_export_marks_changes_and_action_items():
    original = "# Chapter One\n\nThe study examines procurement."
    revised = "# Chapter One\n\nThe study critically examines procurement. [insert verified national statistic]"
    stream, filename = export_revised_chapter_docx(
        original_chapter_text=original,
        revised_chapter_text=revised,
        title="Chapter One",
        strengthening_report="# Chapter Strengthening Report\n\nReview completed.",
        include_strengthening_report=True,
    )
    assert filename.endswith(".docx")
    assert len(stream.getvalue()) > 1000


def test_fallback_report_formats_provider_errors():
    from app.chapter_revision_service import _fallback_report
    report = _fallback_report(
        {},
        [],
        [
            {"provider": "Semantic Scholar", "error": "HTTP Error 429: "},
            {"provider": "openai", "error": "Chapter revision failed: Request timed out."},
        ],
    )
    assert "{'provider'" not in report
    assert "Semantic Scholar: temporary rate limit" in report
    assert "openai: Chapter revision failed" in report
