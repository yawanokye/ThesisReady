from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _reload_for_internal_access(monkeypatch):
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_EMAILS", "aadam@ucc.edu.gh")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_KEY", "123456")
    monkeypatch.setenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET", "internal-test-signing-secret")

    import app.payments.internal_access as internal_access
    import app.payments.guard as guard
    import app.routers.payments as payments_router
    import app.routers.topic_ideas as topic_router
    import app.main as main

    importlib.reload(internal_access)
    importlib.reload(guard)
    importlib.reload(payments_router)
    importlib.reload(topic_router)
    importlib.reload(main)
    return internal_access, guard, main


def test_internal_access_requires_email_and_six_digit_key(monkeypatch):
    internal_access, _guard, _main = _reload_for_internal_access(monkeypatch)

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


def test_internal_access_status_endpoint_unlocks_topic_ideas(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "internal.db"))
    _internal_access, _guard, main = _reload_for_internal_access(monkeypatch)
    client = TestClient(main.app)

    activated = client.post(
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
    assert activated.status_code == 200
    credential = activated.json()
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
    assert payload["remaining"]["draft"] == 999


def test_internal_access_guard_bypasses_payment_quota(monkeypatch):
    internal_access, guard, _main = _reload_for_internal_access(monkeypatch)
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


def test_frontend_contains_developer_access_panels():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    projectready_js = (root / "app/static/projectready_payments.js").read_text()
    topic_html = (root / "app/static/topic_ideas.html").read_text()
    topic_js = (root / "app/static/topic_ideas.js").read_text()

    assert "Developer access" in projectready_js
    assert "prInternalKey" in projectready_js
    assert "activateInternalAccess" in projectready_js
    assert "Developer access" in topic_html
    assert "topicInternalKey" in topic_html
    assert "activateTopicInternalAccess" in topic_js
