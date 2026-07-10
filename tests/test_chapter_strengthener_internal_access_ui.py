from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chapter_strengthener_has_visible_developer_access_panel():
    html = (ROOT / "app/static/chapter_strengthener.html").read_text()
    assert 'id="strengthenerDeveloperAccessPanel"' in html
    assert 'id="strengthenerDeveloperEmail"' in html
    assert 'id="strengthenerDeveloperKey"' in html
    assert 'id="activateStrengthenerDeveloperAccessBtn"' in html
    assert 'projectready_payments.js?v=20260710-internal-access-strengthener-v2' in html


def test_chapter_strengthener_uses_internal_fallback_credentials():
    js = (ROOT / "app/static/chapter_strengthener.js").read_text()
    payments_js = (ROOT / "app/static/projectready_payments.js").read_text()
    assert "activateStrengthenerDeveloperAccess" in js
    assert "productArea: 'chapter_strengthener'" in js
    assert "paymentHeaders(projectId(), chapterNumber(), 'chapter_strengthener')" in js
    assert "getCredential(projectId(), chapterNumber(), 'chapter_strengthener')" in js
    assert "internalCredentialKeys" in payments_js
    assert "saveInternalCredential" in payments_js
