from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_optional_fields_are_collapsible():
    html = (ROOT / "app/static/workspace.html").read_text()
    js = (ROOT / "app/static/app.js").read_text()
    assert 'id="toggleOptionalFieldsBtn"' in html
    assert html.count('data-optional-group') >= 6
    assert "Show more optional fields" in html
    assert "Show more guidance fields" in js
    assert "initialiseOptionalFields" in js


def test_workspace_uses_background_drafting_and_resume():
    html = (ROOT / "app/static/workspace.html").read_text()
    js = (ROOT / "app/static/app.js").read_text()
    assert 'id="backgroundJobPanel"' in html
    assert "/draft-jobs" in js
    assert "X-ProjectReady-Job-Token" in js
    assert "resumeBackgroundDraftIfAvailable" in js
    assert "cancelActiveBackgroundJob" in js


def test_restricted_portal_assets_are_outside_public_static():
    assert (ROOT / "app/internal_assets/portal.html").exists()
    assert (ROOT / "app/internal_assets/module_session.js").exists()
    assert not (ROOT / "app/static/developer_portal.html").exists()
    assert not (ROOT / "app/static/restricted_session.js").exists()
