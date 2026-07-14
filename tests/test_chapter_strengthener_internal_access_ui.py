from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chapter_strengthener_hides_internal_access_and_uses_background_jobs():
    html = (ROOT / "app/static/chapter_strengthener.html").read_text()
    js = (ROOT / "app/static/chapter_strengthener.js").read_text()

    assert "Developer access" not in html
    assert "strengthenerDeveloperAccessPanel" not in html
    assert 'id="strengthenerJobPanel"' in html
    assert "/chapter-strengthener/jobs" in js
    assert "X-ProjectReady-Job-Token" in js
    assert "resumeStrengthenerJobIfAvailable" in js
    assert "restricted_session.js" not in html
    assert "module-session.js" not in html


def test_internal_portal_assets_are_not_in_public_static_directory():
    static_dir = ROOT / "app/static"
    assert not (static_dir / "developer_portal.html").exists()
    assert not (static_dir / "developer_portal.css").exists()
    assert not (static_dir / "developer_portal.js").exists()
    assert (ROOT / "app/internal_assets/portal.html").exists()
    assert (ROOT / "app/internal_assets/module_session.js").exists()
