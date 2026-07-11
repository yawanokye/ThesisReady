from pathlib import Path

from app.scholarly_humanizer import (
    analyse_scholarly_style,
    humanize_scholarly_text,
    validate_humanizer_preservation,
)


def test_humanizer_removes_legacy_artefacts_and_preserves_evidence():
    text = """# 1.2 Background

The present investigation shows that financial literacy plays a crucial role in retirement planning insofar as workers must understand inflation (Lusardi & Mitchell, 2011). That matters. This qualification matters because it keeps the argument tied to the evidence rather than to an unsupported general claim.

Furthermore, the results obtained indicate that 27% of respondents planned for retirement [confirm current Ghana evidence].

Furthermore, as an illustration, workers may understand pension products but remain unable to contribute regularly.

# References

Lusardi, A., & Mitchell, O. S. (2011). Financial literacy. https://example.org/reference
"""
    revised, report = humanize_scholarly_text(text, mode="balanced")

    assert report["preservation_passed"] is True
    assert "That matters" not in revised
    assert "This qualification matters" not in revised
    assert "insofar as" not in revised
    assert "plays a crucial role" not in revised
    assert "27%" in revised
    assert "(Lusardi & Mitchell, 2011)" in revised
    assert "[confirm current Ghana evidence]" in revised
    assert "https://example.org/reference" in revised
    assert report["score_after"] >= report["score_before"]


def test_reference_tail_is_not_rewritten():
    text = """# Discussion

The present investigation uses an example insofar as the evidence permits it.

# References

The present investigation. (2020). As an illustration. https://example.org
"""
    revised, _ = humanize_scholarly_text(text, mode="balanced")
    reference_tail = revised.split("# References", 1)[1]
    assert "The present investigation. (2020). As an illustration." in reference_tail


def test_off_mode_returns_text_unchanged():
    text = "The present investigation matters."
    revised, report = humanize_scholarly_text(text, mode="off")
    assert revised == text
    assert report["applied"] is False


def test_preservation_gate_rejects_number_or_citation_changes():
    original = "The sample contained 515 respondents (Adam, 2026)."
    candidate = "The sample contained 500 respondents (Adam, 2025)."
    valid, issues = validate_humanizer_preservation(original, candidate)
    assert valid is False
    assert any("years" in issue or "numbers" in issue or "citation" in issue for issue in issues)


def test_style_diagnostic_identifies_stock_phrases():
    weak = "Furthermore, it is important to note that this study plays a crucial role. That matters."
    strong = "The evidence indicates a clear association, although the estimate remains context dependent."
    assert analyse_scholarly_style(strong)["score"] > analyse_scholarly_style(weak)["score"]


def test_humanizer_controls_are_available_in_both_workspaces():
    workspace = Path("app/static/workspace.html").read_text(encoding="utf-8")
    strengthener = Path("app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    app_js = Path("app/static/app.js").read_text(encoding="utf-8")
    strengthener_js = Path("app/static/chapter_strengthener.js").read_text(encoding="utf-8")

    assert 'id="humanizerMode"' in workspace
    assert 'id="strengthenerHumanizerMode"' in strengthener
    assert "humanizer_mode" in app_js
    assert "humanizer_mode" in strengthener_js


def test_backend_python_is_not_publicly_served_from_static():
    assert not list(Path("app/static").glob("*.py"))
