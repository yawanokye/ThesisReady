from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_topic_ideas_clear_removes_persisted_form_and_cancels_old_job():
    js = (ROOT / "app/static/topic_ideas.js").read_text(encoding="utf-8")
    assert "function clearTopicFormDraft()" in js
    assert "storage.removeItem(TOPIC_FORM_STORAGE_KEY)" in js
    assert "activeGenerationController.abort()" in js
    assert "activeGenerationSequence += 1" in js
    assert "generationSequence !== activeGenerationSequence" in js
    assert "saveTopicFormDraftForCheckout()" in js
    assert "saveTopicFormDraft();" not in js


def test_topic_ideas_does_not_restore_old_form_on_normal_refresh():
    js = (ROOT / "app/static/topic_ideas.js").read_text(encoding="utf-8")
    assert "restoreTopicFormDraft({ paymentReturn: isPaymentReturn })" in js
    assert "if (!paymentReturn)" in js
    assert "clearTopicFormDraft();" in js


def test_topic_ideas_clear_button_and_cache_version_are_updated():
    html = (ROOT / "app/static/topic_ideas.html").read_text(encoding="utf-8")
    assert 'autocomplete="off"' in html
    assert "Clear and start new job" in html
    assert "20260718-all-clear-trend-v1" in html
