from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_has_clear_and_start_new_job_flow():
    html = (ROOT / "app/static/workspace.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="clearWorkspaceBtn"' in html
    assert "Clear and start new job" in html
    assert "function clearWorkspaceStoredJobState()" in js
    assert "function resetWorkspaceBrowserFields()" in js
    assert "WORKSPACE_NEW_JOB_PARAM" in js
    assert "storage.removeItem(CURRENT_PROJECT_STORAGE_KEY)" in js
    assert "projectready-background-job:" in js
    assert "function ensureWorkspaceClearButton()" in js
    assert "workspace-clear-action" in js
    assert "20260718-workspace-clear-visible-v2" in html


def test_strengthener_has_clean_new_job_flow():
    html = (ROOT / "app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/chapter_strengthener.js").read_text(encoding="utf-8")
    assert 'id="revisionForm" class="card form-card" autocomplete="off"' in html
    assert "Clear and start new job" in html
    assert "function clearStrengthenerStoredJobState()" in js
    assert "function resetStrengthenerForNewJob()" in js
    assert "STRENGTHENER_NEW_JOB_PARAM" in js
    assert "storage.removeItem(PROJECT_STORAGE_KEY)" in js
    assert "projectready-strengthener-job:" in js
    assert "20260718-all-clear-trend-v1" in html


def test_topic_ideas_keeps_clear_new_job_and_updated_cache_version():
    html = (ROOT / "app/static/topic_ideas.html").read_text(encoding="utf-8")
    assert "Clear and start new job" in html
    assert "20260718-all-clear-trend-v1" in html
