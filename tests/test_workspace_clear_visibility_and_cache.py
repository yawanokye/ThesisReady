from fastapi.testclient import TestClient

from app.main import app


def test_workspace_html_is_not_cached_and_contains_visible_clear_control():
    client = TestClient(app)
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    assert 'id="clearWorkspaceBtn"' in response.text
    assert "Clear and start new job" in response.text
    assert "workspace-clear-action" in response.text


def test_workspace_javascript_can_restore_clear_button_when_html_is_stale():
    client = TestClient(app)
    response = client.get("/static/app.js?v=20260718-workspace-clear-visible-v2")
    assert response.status_code == 200
    assert "function ensureWorkspaceClearButton()" in response.text
    assert 'button.id = "clearWorkspaceBtn"' in response.text
