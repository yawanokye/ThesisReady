from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PORTAL_PATH = "/internal/test-strengthener-cookie-4a8e21"


def _reload_app(monkeypatch, database_path: str):
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_EMAILS", "aadam@ucc.edu.gh")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_KEY", "123456")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET", "internal-cookie-test-secret-that-is-long")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_PORTAL_PATH", PORTAL_PATH)
    monkeypatch.setenv("PROJECTREADY_COOKIE_SECURE", "0")
    monkeypatch.setenv("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "1")
    monkeypatch.setenv("DATABASE_URL", database_path)
    monkeypatch.delenv("PROJECTREADY_SQLITE_DB_PATH", raising=False)

    import app.database as database
    import app.jobs.store as job_store
    import app.payments.internal_access as internal_access
    import app.payments.guard as guard
    import app.internal_portal as internal_portal
    import app.routers.projects as projects
    import app.routers.chapter_strengthener as chapter_strengthener
    import app.routers.jobs as jobs
    import app.main as main

    for module in (
        database,
        job_store,
        internal_access,
        guard,
        internal_portal,
        projects,
        chapter_strengthener,
        jobs,
        main,
    ):
        importlib.reload(module)
    return main, job_store


def test_private_strengthener_keeps_private_routes(monkeypatch, tmp_path):
    main, _store = _reload_app(monkeypatch, str(tmp_path / "private-strengthener.db"))
    with TestClient(main.app) as client:
        login = client.post(
            PORTAL_PATH + "/api/session",
            json={"email": "aadam@ucc.edu.gh", "key": "123456"},
        )
        assert login.status_code == 200
        page = client.get(PORTAL_PATH + "/chapter-strengthener")
        assert page.status_code == 200
        assert f'href="{PORTAL_PATH}/workspace"' in page.text
        assert f'href="{PORTAL_PATH}/chapter-strengthener"' in page.text
        assert f'href="{PORTAL_PATH}/topic-ideas"' in page.text
        assert 'name="projectready-internal-module-path"' in page.text
        assert f'content="{PORTAL_PATH}/chapter-strengthener"' in page.text
        assert "20260718-strengthener-access-v4" in page.text


def test_internal_cookie_queues_strengthener_without_payment_headers(monkeypatch, tmp_path):
    main, job_store = _reload_app(monkeypatch, str(tmp_path / "cookie-queue.db"))
    with TestClient(main.app) as client:
        login = client.post(
            PORTAL_PATH + "/api/session",
            json={"email": "aadam@ucc.edu.gh", "key": "123456"},
        )
        assert login.status_code == 200

        project = client.post(
            "/api/projects",
            json={
                "title": "Internal Strengthener Test",
                "level": "Bachelors",
                "academic_integrity_confirmed": True,
                "user_contribution_confirmed": True,
            },
        )
        assert project.status_code == 200
        project_id = project.json()["id"]

        queued = client.post(
            f"/api/projects/{project_id}/chapter-strengthener/jobs",
            json={
                "thesis_title": "Internal Strengthener Test",
                "chapter_title": "Introduction",
                "chapter_type": "1. Introduction",
                "chapter_text": "This is an existing working chapter supplied for authorised internal testing. " * 4,
                "academic_level": "Bachelors",
                "academic_integrity_confirmed": True,
                "user_contribution_confirmed": True,
                "include_source_search": False,
            },
        )
        assert queued.status_code == 202, queued.text
        job = job_store.get_job(queued.json()["job"]["id"], include_payload=True)
        claim = (job.get("payload") or {}).get("_preauthorized_claim") or {}
        assert claim.get("internal_access") is True
        assert claim.get("claimed") is False


def test_strengthener_client_preserves_internal_path_and_in_memory_credential():
    strengthener_js = (ROOT / "app/static/chapter_strengthener.js").read_text()
    payments_js = (ROOT / "app/static/projectready_payments.js").read_text()
    module_js = (ROOT / "app/internal_assets/module_session.js").read_text()

    assert "function strengthenerPagePath()" in strengthener_js
    assert "new URL(strengthenerPagePath(), window.location.origin)" in strengthener_js
    assert "history.replaceState({}, document.title, strengthenerPagePath())" in strengthener_js
    assert "Internal developer access is active for Chapter Strengthener" in strengthener_js
    assert "window.ProjectReadyInternalCredential" in payments_js
    assert '"chapter_strengthener"' in module_js
