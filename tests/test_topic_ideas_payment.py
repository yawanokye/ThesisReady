from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def test_topic_ideas_plan_prices(monkeypatch):
    monkeypatch.setenv("PROJECTREADY_TOPIC_IDEAS_USD", "1.50")
    monkeypatch.setenv("PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS", "10.00")
    import app.payments.entitlements as entitlements
    import app.payments.paystack as paystack
    importlib.reload(entitlements)
    importlib.reload(paystack)

    plan = entitlements.get_plan("topic_ideas_access")
    assert plan["amount"] == 1.50
    assert plan["drafts"] == 1
    assert plan["validity_days"] == 30
    assert entitlements.normalise_purchase_mode("topic-ideas") == "topic_ideas"

    charge = paystack.get_paystack_charge("topic_ideas_access")
    assert charge["amount"] == 10.00
    assert charge["currency"] == "GHS"


def test_topic_ideas_requires_paid_access(tmp_path, monkeypatch):
    db = tmp_path / "topic-payment.db"
    monkeypatch.setenv("DATABASE_URL", str(db))

    import app.database as database
    import app.payments.store as store
    import app.payments.guard as guard
    import app.routers.topic_ideas as topic_router
    import app.main as main
    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(guard)
    importlib.reload(topic_router)
    importlib.reload(main)

    client = TestClient(main.app)
    response = client.post("/api/topic-ideas", json={"research_area": "financial literacy"})
    assert response.status_code == 402
    assert response.json()["detail"]["reason"] == "topic_ideas_payment_required"


def test_topic_ideas_paid_credit_is_consumed_once(tmp_path, monkeypatch):
    db = tmp_path / "topic-payment.db"
    monkeypatch.setenv("DATABASE_URL", str(db))

    import app.database as database
    import app.payments.store as store
    import app.payments.guard as guard
    import app.routers.topic_ideas as topic_router
    import app.main as main
    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(guard)
    importlib.reload(topic_router)
    importlib.reload(main)

    purchase = store.create_pending_purchase(
        user_email="student@example.com",
        project_id="topic-ideas-test",
        chapter_number=99,
        chapter_title="Topic Ideas Access",
        academic_level="Topic Ideas",
        plan_key="topic_ideas_access",
        amount=10.00,
        currency="GHS",
        display_amount=1.50,
        display_currency="USD",
        payment_provider="paystack",
        provider_reference="PRAI-PS-TOPICTEST",
        metadata={"purchase_mode": "topic_ideas"},
        database_url=str(db),
    )
    store.activate_purchase(
        provider_reference="PRAI-PS-TOPICTEST",
        verified_amount=10.00,
        verified_currency="GHS",
        provider_payload={"status": "success"},
        database_url=str(db),
    )

    monkeypatch.setattr(topic_router, "generate_topic_ideas", lambda payload: {"ideas": [{"title": "Test"}]})
    client = TestClient(main.app)
    headers = {
        "X-ProjectReady-Purchase-ID": purchase["id"],
        "X-ProjectReady-Access-Token": purchase["access_token"],
        "X-Idempotency-Key": "topic-generation-1",
    }
    first = client.post("/api/topic-ideas", json={"research_area": "financial literacy"}, headers=headers)
    assert first.status_code == 200
    second = client.post("/api/topic-ideas", json={"research_area": "financial literacy"}, headers={**headers, "X-Idempotency-Key": "topic-generation-2"})
    assert second.status_code == 402


def test_topic_ideas_checkout_routes_ghana_to_paystack(tmp_path, monkeypatch):
    db = tmp_path / "topic-checkout.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS", "10.00")

    import app.database as database
    import app.payments.store as store
    import app.payments.paystack as paystack
    import app.routers.payments as payments_router
    import app.main as main
    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(paystack)
    importlib.reload(payments_router)
    importlib.reload(main)

    def fake_paystack(purchase):
        return {
            "ok": True,
            "provider": "paystack",
            "checkout_url": "https://checkout.example/paystack",
            "purchase_id": purchase["id"],
            "access_token": purchase["access_token"],
            "amount": purchase["amount"],
            "currency": purchase["currency"],
        }

    monkeypatch.setattr(payments_router, "initialize_paystack_payment", fake_paystack)
    client = TestClient(main.app)
    response = client.post(
        "/api/topic-ideas/checkout",
        json={"email": "student@example.com", "market": "ghana", "return_path": "/topic-ideas"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "paystack"
    assert data["amount"] == 10.0
    assert data["currency"] == "GHS"
    assert data["access_id"].startswith("topic-ideas-")


def test_topic_ideas_checkout_routes_international_to_stripe(tmp_path, monkeypatch):
    db = tmp_path / "topic-checkout.db"
    monkeypatch.setenv("DATABASE_URL", str(db))

    import app.database as database
    import app.payments.store as store
    import app.routers.payments as payments_router
    import app.main as main
    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(payments_router)
    importlib.reload(main)

    def fake_stripe(purchase, database_url=""):
        return {
            "ok": True,
            "provider": "stripe",
            "checkout_url": "https://checkout.example/stripe",
            "purchase_id": purchase["id"],
            "access_token": purchase["access_token"],
            "amount": purchase["amount"],
            "currency": purchase["currency"],
        }

    monkeypatch.setattr(payments_router, "initialize_stripe_payment", fake_stripe)
    client = TestClient(main.app)
    response = client.post(
        "/api/topic-ideas/checkout",
        json={"email": "student@example.com", "market": "international", "return_path": "/topic-ideas"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "stripe"
    assert data["amount"] == 1.5
    assert data["currency"] == "USD"
