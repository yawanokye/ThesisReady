from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PORTAL_PATH = "/internal/test-private-portal-8f3a91"


def _reload_for_internal_access(monkeypatch, database_path: str = ""):
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_EMAILS", "aadam@ucc.edu.gh")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_KEY", "123456")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET", "internal-test-signing-secret-that-is-long")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_PORTAL_PATH", PORTAL_PATH)
    monkeypatch.setenv("PROJECTREADY_ENABLE_LEGACY_INTERNAL_ACCESS_ENDPOINT", "0")
    monkeypatch.setenv("PROJECTREADY_COOKIE_SECURE", "0")
    if database_path:
        monkeypatch.setenv("DATABASE_URL", database_path)
        monkeypatch.delenv("PROJECTREADY_SQLITE_DB_PATH", raising=False)

    import app.database as database
    import app.payments.internal_access as internal_access
    import app.payments.guard as guard
    import app.internal_portal as internal_portal
    import app.routers.payments as payments_router
    import app.routers.topic_ideas as topic_router
    import app.main as main

    importlib.reload(database)
    importlib.reload(internal_access)
    importlib.reload(guard)
    importlib.reload(payments_router)
    importlib.reload(topic_router)
    importlib.reload(internal_portal)
    importlib.reload(main)
    return internal_access, guard, internal_portal, main


def test_internal_access_requires_email_and_six_digit_key(monkeypatch):
    internal_access, _guard, _portal, _main = _reload_for_internal_access(monkeypatch)

    denied_email = None
    try:
        internal_access.issue_internal_access(
            email="student@example.com",
            key="123456",
            product_area="topic_ideas",
            chapter_number=99,
        )
    except PermissionError as exc:
        denied_email = str(exc)
    assert denied_email and "not authorised" in denied_email

    denied_key = None
    try:
        internal_access.issue_internal_access(
            email="aadam@ucc.edu.gh",
            key="654321",
            product_area="topic_ideas",
            chapter_number=99,
        )
    except PermissionError as exc:
        denied_key = str(exc)
    assert denied_key and "invalid" in denied_key.lower()


def test_restricted_portal_issues_cookie_and_module_access(monkeypatch, tmp_path):
    _internal_access, _guard, _portal, main = _reload_for_internal_access(
        monkeypatch, str(tmp_path / "internal.db")
    )
    with TestClient(main.app) as client:
        page = client.get(PORTAL_PATH)
        assert page.status_code == 200
        assert "Internal access portal" in page.text
        assert page.headers.get("x-robots-tag") == "noindex, nofollow, noarchive"
        assert "frame-ancestors 'none'" in page.headers.get("content-security-policy", "")

        denied = client.post(
            "/api/internal/session",
            json={"email": "aadam@ucc.edu.gh", "key": "654321"},
        )
        assert denied.status_code == 404

        activated = client.post(
            "/api/internal/session",
            json={"email": "aadam@ucc.edu.gh", "key": "123456"},
        )
        assert activated.status_code == 200
        assert "pr_internal_portal_session" in client.cookies

        private_workspace = client.get(PORTAL_PATH + "/workspace")
        assert private_workspace.status_code == 200
        assert PORTAL_PATH + "/module-session.js" in private_workspace.text
        public_workspace = client.get("/workspace")
        assert "module-session.js" not in public_workspace.text

        module = client.post("/api/internal/module-access", json={})
        assert module.status_code == 200
        credential = module.json()
        assert credential["provider"] == "internal_admin"
        assert credential["purchase_id"].startswith("pr-internal-v1:")

        status = client.post(
            "/api/topic-ideas/payment-status",
            json={
                "purchase_id": credential["purchase_id"],
                "access_token": credential["access_token"],
            },
        )
        assert status.status_code == 200
        payload = status.json()
        assert payload["allowed"] is True
        assert payload["access_type"] == "internal_admin"


def test_legacy_public_internal_access_endpoint_is_hidden(monkeypatch, tmp_path):
    _internal_access, _guard, _portal, main = _reload_for_internal_access(
        monkeypatch, str(tmp_path / "internal-hidden.db")
    )
    with TestClient(main.app) as client:
        response = client.post(
            "/api/payments/internal-access",
            json={
                "email": "aadam@ucc.edu.gh",
                "key": "123456",
                "product_area": "topic_ideas",
                "project_id": "topic-ideas-internal",
                "chapter_number": 99,
                "chapter_title": "Topic Ideas Access",
            },
        )
        assert response.status_code == 404


def test_internal_access_guard_bypasses_payment_quota(monkeypatch):
    internal_access, guard, _portal, _main = _reload_for_internal_access(monkeypatch)
    credential = internal_access.issue_internal_access(
        email="aadam@ucc.edu.gh",
        key="123456",
        product_area="thesis_workspace",
        project_id="project-123",
        chapter_number=2,
        chapter_title="Literature Review",
    )

    with guard.paid_chapter_action(
        purchase_id=credential["purchase_id"],
        access_token=credential["access_token"],
        project_id="project-123",
        chapter_number=2,
        chapter_title="Literature Review",
        action="draft",
        metadata={"product_area": "thesis_workspace"},
    ) as claim:
        assert claim["internal_access"] is True
        assert claim["claimed"] is False


def test_public_frontend_contains_no_developer_access_controls():
    public_files = [
        ROOT / "app/static/workspace.html",
        ROOT / "app/static/chapter_strengthener.html",
        ROOT / "app/static/topic_ideas.html",
        ROOT / "app/static/projectready_payments.js",
        ROOT / "app/static/chapter_strengthener.js",
        ROOT / "app/static/topic_ideas.js",
    ]
    public_text = "\n".join(path.read_text() for path in public_files)
    assert "Developer access" not in public_text
    assert "activateInternalAccess" not in public_text
    assert "/api/payments/internal-access" not in public_text
    assert "PROJECTREADY_INTERNAL_PORTAL_PATH" not in public_text
