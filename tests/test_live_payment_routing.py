from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "projectready-live-payments.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_live_paystack_example")
    monkeypatch.setenv("PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS", "10.00")
    monkeypatch.setenv("STRIPE_LIVE_SECRET_KEY", "sk_live_example")
    monkeypatch.setenv("STRIPE_LIVE_WEBHOOK_SECRET", "whsec_example")
    monkeypatch.delenv("PROJECTREADY_STRIPE_MODE", raising=False)
    monkeypatch.delenv("PROJECTREADY_FORCE_STRIPE", raising=False)
    monkeypatch.delenv("PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY", raising=False)
    monkeypatch.delenv("PROJECTREADY_TOPIC_IDEAS_TRIAL_KEY", raising=False)

    import app.database as database
    import app.payments.store as store
    import app.payments.router as payment_router
    import app.payments.stripe_provider as stripe_provider
    import app.routers.payments as payments_router
    import app.main as main

    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(payment_router)
    importlib.reload(stripe_provider)
    importlib.reload(payments_router)
    importlib.reload(main)
    return db, store, payment_router, stripe_provider, main


def test_live_routing_uses_paystack_for_africa_and_stripe_elsewhere(tmp_path, monkeypatch):
    db, store, payment_router, stripe_provider, main = _reload_app(tmp_path, monkeypatch)
    assert payment_router.choose_payment_provider("GH") == "paystack"
    assert payment_router.choose_payment_provider("NG") == "paystack"
    assert payment_router.choose_payment_provider("US") == "stripe"
    assert payment_router.choose_payment_provider("GB") == "stripe"

    environment = stripe_provider.stripe_environment_payload()
    assert environment["mode"] == "live"
    assert environment["test_mode"] is False
    assert environment["force_stripe"] is False


def test_topic_ideas_has_no_admin_trial_endpoint_or_panel(tmp_path, monkeypatch):
    db, store, payment_router, stripe_provider, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)

    plan = client.get("/api/topic-ideas/access-plan")
    assert plan.status_code == 200
    body = plan.json()
    assert "trial" not in body
    assert body["ghana"]["provider"] == "paystack"
    assert body["international"]["provider"] == "stripe"
    assert body["payment_environment"]["mode"] == "live"

    missing_endpoint = client.post(
        "/api/topic-ideas/activate-trial",
        json={"email": "admin@example.com", "trial_key": "anything"},
    )
    assert missing_endpoint.status_code == 404

    page = client.get("/topic-ideas")
    assert page.status_code == 200
    assert "Administrator trial access" not in page.text
    assert "Stripe test mode" not in page.text
    assert "Restore paid access" in page.text
