from pathlib import Path

from app.scholarly_humanizer import (
    analyse_scholarly_style,
    humanize_scholarly_text,
    humanizer_variation_profile,
    scholarly_humanizer_prompt_rules,
    validate_humanizer_preservation,
    variation_targets_met,
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


def test_humanizer_improves_repetitive_academic_framing_without_changing_citations():
    text = """# 1.2 Background

Furthermore, it is important to note that the present study plays a crucial role in examining teacher assessment (Mensah, 2024). Furthermore, the present study is able to show how assessment operates in order to support learning. Furthermore, it is against this background that the present study examines the issue.
"""
    revised, report = humanize_scholarly_text(text, mode="balanced")
    assert "it is important to note" not in revised.lower()
    assert "plays a crucial role" not in revised.lower()
    assert "is able to" not in revised.lower()
    assert revised.lower().count("furthermore") <= 2
    assert "(Mensah, 2024)" in revised
    assert report["score_after"] >= report["score_before"]


def test_long_chapter_is_split_into_protected_section_batches():
    from app.scholarly_humanizer import build_humanizer_batches

    text = """# CHAPTER 2

# 2.1 Introduction

""" + ("The literature presents a contested position. " * 120) + """

# 2.2 Theoretical Review

""" + ("The theory provides a basis for comparison. " * 120) + """

# References

Mensah, A. (2024). Example study.
"""
    batches = build_humanizer_batches(text, max_words=700)
    assert len(batches) >= 3
    assert any(batch["protected"] for batch in batches)
    assert all(batch["word_count"] > 0 for batch in batches)


def test_high_perplexity_and_burstiness_are_default_targets(monkeypatch):
    monkeypatch.delenv("PROJECTREADY_HUMANIZER_PERPLEXITY_LEVEL", raising=False)
    monkeypatch.delenv("PROJECTREADY_HUMANIZER_BURSTINESS_LEVEL", raising=False)
    profile = humanizer_variation_profile()
    assert profile["perplexity_level"] == "high"
    assert profile["burstiness_level"] == "high"
    assert profile["lexical_diversity_target"] >= 0.60
    assert profile["sentence_length_cv_target"] >= 0.45


def test_diagnostic_reports_variation_metrics():
    text = (
        "Clear evidence matters. "
        "The first estimate remains cautious because the sample is limited and the institutional context differs across schools. "
        "A longer synthesis sentence then connects the empirical pattern, the theoretical explanation and the practical implication without overstating causality. "
        "Results vary. "
        "Different methods produce different forms of evidence, especially when measurement choices alter the meaning of the construct being assessed."
    )
    report = analyse_scholarly_style(text)
    assert "lexical_diversity_msttr" in report
    assert "sentence_length_cv" in report
    assert "paragraph_length_cv" in report
    assert "short_sentence_ratio" in report
    assert "long_sentence_ratio" in report
    assert isinstance(report["variation_targets_met"], bool)


def test_humanizer_prompt_requires_high_controlled_variation():
    rules = " ".join(scholarly_humanizer_prompt_rules()).lower()
    assert "high controlled perplexity" in rules
    assert "high controlled burstiness" in rules
    assert "rare synonyms" in rules


def test_variation_gate_rejects_uniform_report():
    profile = humanizer_variation_profile()
    weak = {
        "lexical_diversity_msttr": 0.30,
        "sentence_length_cv": 0.10,
        "paragraph_length_cv": 0.10,
        "short_sentence_ratio": 0.0,
        "long_sentence_ratio": 0.0,
    }
    assert variation_targets_met(weak, profile) is False
