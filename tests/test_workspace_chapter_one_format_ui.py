from pathlib import Path


def test_workspace_exposes_chapter_one_format_controls():
    html = Path("app/static/workspace.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'id="backgroundStructure"' in html
    assert 'id="purposeStatementStyle"' in html
    assert 'id="expectedChapters"' in html
    assert 'id="automaticSourceSupport"' in html
    assert "background_structure" in js
    assert "purpose_statement_style" in js
    assert "automatic_source_support" in js
    assert "expected_chapters" in js
