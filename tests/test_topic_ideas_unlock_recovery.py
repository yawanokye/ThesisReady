from __future__ import annotations

import importlib
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "topic-unlock.db"
    monkeypatch.setenv("DATABASE_URL", str(db))

    import app.database as database
    import app.payments.store as store
    import app.payments.guard as guard
    import app.routers.topic_ideas as topic_router
    import app.routers.payments as payments_router
    import app.main as main

    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(guard)
    importlib.reload(topic_router)
    importlib.reload(payments_router)
    importlib.reload(main)
    return db, store, payments_router, main


def _paid_topic_purchase(store, db, *, email="student@example.com", provider="stripe"):
    purchase = store.create_pending_purchase(
        user_email=email,
        project_id="topic-ideas-recovery-test",
        chapter_number=99,
        chapter_title="Topic Ideas Access",
        academic_level="Topic Ideas",
        plan_key="topic_ideas_access",
        amount=1.50 if provider == "stripe" else 10.00,
        currency="USD" if provider == "stripe" else "GHS",
        display_amount=1.50,
        display_currency="USD",
        payment_provider=provider,
        provider_reference="PRAI-ST-HANDOFFTEST" if provider == "stripe" else "PRAI-PS-HANDOFFTEST",
        metadata={"purchase_mode": "topic_ideas", "return_path": "/topic-ideas"},
        database_url=str(db),
    )
    store.activate_purchase(
        provider_reference=purchase["provider_reference"],
        verified_amount=purchase["amount"],
        verified_currency=purchase["currency"],
        provider_payload={"status": "paid"},
        database_url=str(db),
    )
    return purchase


def test_payment_return_handoff_redeems_once_and_unlocks(tmp_path, monkeypatch):
    db, store, payments_router, main = _reload_app(tmp_path, monkeypatch)
    purchase = _paid_topic_purchase(store, db)
    handoff = store.create_access_handoff(purchase["id"], database_url=str(db))

    client = TestClient(main.app)
    redeemed = client.post("/api/topic-ideas/redeem-handoff", json={"handoff": handoff})
    assert redeemed.status_code == 200
    credential = redeemed.json()
    assert credential["purchase_id"] == purchase["id"]
    assert credential["access_token"]
    assert credential["status"]["allowed"] is True
    assert credential["status"]["remaining"]["draft"] == 1

    repeated = client.post("/api/topic-ideas/redeem-handoff", json={"handoff": handoff})
    assert repeated.status_code == 403

    status = client.post(
        "/api/topic-ideas/payment-status",
        json={"purchase_id": credential["purchase_id"], "access_token": credential["access_token"]},
    )
    assert status.status_code == 200
    assert status.json()["allowed"] is True


def test_paid_access_can_be_restored_with_purchase_id_and_payment_email(tmp_path, monkeypatch):
    db, store, payments_router, main = _reload_app(tmp_path, monkeypatch)
    purchase = _paid_topic_purchase(store, db, email="buyer@example.com", provider="paystack")

    client = TestClient(main.app)
    restored = client.post(
        "/api/topic-ideas/recover-access",
        json={"purchase_id": purchase["id"], "email": "buyer@example.com"},
    )
    assert restored.status_code == 200
    data = restored.json()
    assert data["purchase_id"] == purchase["id"]
    assert data["access_token"] != purchase["access_token"]
    assert data["status"]["allowed"] is True

    old_status = client.post(
        "/api/topic-ideas/payment-status",
        json={"purchase_id": purchase["id"], "access_token": purchase["access_token"]},
    )
    assert old_status.status_code == 403

    wrong_email = client.post(
        "/api/topic-ideas/recover-access",
        json={"purchase_id": purchase["id"], "email": "other@example.com"},
    )
    assert wrong_email.status_code == 403


def test_topic_success_redirect_contains_secure_handoff(tmp_path, monkeypatch):
    db, store, payments_router, main = _reload_app(tmp_path, monkeypatch)
    purchase = _paid_topic_purchase(store, db)

    response = payments_router._successful_payment_redirect(purchase, "stripe")
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert parsed.path == "/topic-ideas"
    assert params["payment"] == ["success"]
    assert params["purchase_id"] == [purchase["id"]]
    assert len(params["handoff"][0]) >= 20
    assert purchase["access_token"] not in location


def test_topic_page_disables_stale_html_cache_and_loads_new_unlock_script(tmp_path, monkeypatch):
    db, store, payments_router, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    response = client.get("/topic-ideas")
    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    assert "20260717-strict-resources-docx-v2" in response.text
    assert "Restore paid access" in response.text
    assert "Administrator trial access" not in response.text
    assert "Stripe test mode" not in response.text
