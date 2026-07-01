from __future__ import annotations

import importlib
import json
from fastapi.testclient import TestClient


def _reload_test_app(tmp_path, monkeypatch):
    db = tmp_path / "projectready-stripe-test.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.delenv("PROJECTREADY_SQLITE_DB_PATH", raising=False)
    monkeypatch.delenv("PROJECTREADY_SQLITE_PAYMENT_DB", raising=False)
    monkeypatch.setenv("APP_BASE_URL", "https://staging.projectreadyai.com")
    monkeypatch.setenv("PROJECTREADY_STRIPE_MODE", "test")
    monkeypatch.setenv("PROJECTREADY_FORCE_STRIPE", "1")
    monkeypatch.setenv("PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY", "private-stripe-test-key-123")
    monkeypatch.setenv("STRIPE_TEST_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_TEST_WEBHOOK_SECRET", "whsec_example")

    import app.database as database
    import app.payments.store as store
    import app.payments.router as provider_router
    import app.payments.stripe_provider as stripe_provider
    import app.routers.payments as payments
    import app.main as main

    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(provider_router)
    importlib.reload(stripe_provider)
    importlib.reload(payments)
    importlib.reload(main)

    database.init_db()
    with database.get_conn() as conn:
        for project_id in ("chapter-project", "revision-project"):
            conn.execute(
                """
                INSERT INTO projects (id, title, profile_json, selected_sections_json, drafts_json, checks_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "Stripe test project",
                    json.dumps({"level": "Bachelors"}),
                    "{}",
                    "{}",
                    "{}",
                ),
            )
        conn.commit()
    return db, database, store, provider_router, stripe_provider, payments, main


def _fake_checkout(purchase, database_url=""):
    return {
        "ok": True,
        "provider": "stripe",
        "payment_environment": "test",
        "test_mode": True,
        "checkout_url": "https://checkout.stripe.test/session",
        "session_id": "cs_test_example",
        "purchase_id": purchase["id"],
        "access_token": purchase["access_token"],
        "amount": purchase["amount"],
        "currency": purchase["currency"],
    }


def test_test_mode_forces_ghana_to_stripe_and_hides_secret(tmp_path, monkeypatch):
    _, _, _, provider_router, _, _, main = _reload_test_app(tmp_path, monkeypatch)
    client = TestClient(main.app)

    environment = client.get("/api/payments/environment")
    assert environment.status_code == 200
    data = environment.json()
    assert data["mode"] == "test"
    assert data["force_stripe"] is True
    assert data["test_checkout_key_required"] is True
    assert "private-stripe-test-key-123" not in environment.text
    assert provider_router.choose_payment_provider("GH") == "stripe"


def test_all_three_paid_paths_create_stripe_test_checkouts(tmp_path, monkeypatch):
    db, _, store, _, _, payments, main = _reload_test_app(tmp_path, monkeypatch)
    monkeypatch.setattr(payments, "initialize_stripe_payment", _fake_checkout)
    client = TestClient(main.app)

    missing_key = client.post(
        "/api/topic-ideas/checkout",
        json={"email": "buyer@example.com", "market": "ghana", "return_path": "/topic-ideas"},
    )
    assert missing_key.status_code == 403

    topic = client.post(
        "/api/topic-ideas/checkout",
        json={
            "email": "buyer@example.com",
            "market": "ghana",
            "return_path": "/topic-ideas",
            "test_access_key": "private-stripe-test-key-123",
        },
    )
    assert topic.status_code == 200
    assert topic.json()["provider"] == "stripe"
    assert topic.json()["currency"] == "USD"
    assert topic.json()["payment_environment"] == "test"

    chapter = client.post(
        "/api/payments/checkout",
        json={
            "email": "buyer@example.com",
            "billing_country": "GH",
            "academic_level": "Bachelors",
            "project_id": "chapter-project",
            "chapter_number": 2,
            "chapter_title": "Literature Review",
            "plan_key": "bachelors_chapter",
            "purchase_mode": "chapter",
            "return_path": "/workspace",
            "test_access_key": "private-stripe-test-key-123",
        },
    )
    assert chapter.status_code == 200
    assert chapter.json()["provider"] == "stripe"
    assert chapter.json()["purchase_mode"] == "chapter"
    assert chapter.json()["payment_environment"] == "test"

    revision = client.post(
        "/api/payments/checkout",
        json={
            "email": "buyer@example.com",
            "billing_country": "GH",
            "academic_level": "Bachelors",
            "project_id": "revision-project",
            "chapter_number": 2,
            "chapter_title": "Literature Review",
            "plan_key": "bachelors_revision",
            "purchase_mode": "revision_only",
            "return_path": "/chapter-strengthener",
            "test_access_key": "private-stripe-test-key-123",
        },
    )
    assert revision.status_code == 200
    assert revision.json()["provider"] == "stripe"
    assert revision.json()["purchase_mode"] == "revision_only"
    assert revision.json()["payment_environment"] == "test"

    for response in (topic, chapter, revision):
        purchase = store.get_purchase(response.json()["purchase_id"], database_url=str(db))
        assert purchase["payment_provider"] == "stripe"
        assert purchase["metadata_json"]["payment_environment"] == "test"


def test_signed_test_sessions_activate_correct_entitlements(tmp_path, monkeypatch):
    db, _, store, _, stripe_provider, _, _ = _reload_test_app(tmp_path, monkeypatch)
    cases = [
        ("topic_ideas_access", "topic_ideas", 99, "Topic Ideas Access", {"draft": 1, "revision": 0, "compliance": 0, "export": 0}),
        ("bachelors_chapter", "chapter", 2, "Literature Review", {"draft": 1, "revision": 1, "compliance": 1, "export": 1}),
        ("bachelors_revision", "revision_only", 2, "Literature Review", {"draft": 0, "revision": 1, "compliance": 1, "export": 1}),
    ]

    for index, (plan_key, mode, chapter_number, chapter_title, expected_remaining) in enumerate(cases, start=1):
        amount = 1.50 if plan_key == "topic_ideas_access" else (2.99 if plan_key == "bachelors_revision" else 4.99)
        project_id = f"entitlement-{index}"
        reference = f"PRAI-ST-test-{index}"
        purchase = store.create_pending_purchase(
            user_email="buyer@example.com",
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            academic_level="Topic Ideas" if plan_key == "topic_ideas_access" else "Bachelors",
            plan_key=plan_key,
            amount=amount,
            currency="USD",
            display_amount=amount,
            display_currency="USD",
            payment_provider="stripe",
            provider_reference=reference,
            metadata={"purchase_mode": mode, "payment_environment": "test"},
            database_url=str(db),
        )
        store.set_checkout_session(purchase["id"], f"cs_test_{index}", database_url=str(db))
        session = {
            "id": f"cs_test_{index}",
            "livemode": False,
            "client_reference_id": purchase["id"],
            "amount_total": int(round(amount * 100)),
            "currency": "usd",
            "payment_status": "paid",
            "customer_email": "buyer@example.com",
            "customer_details": {"email": "buyer@example.com"},
            "metadata": {
                "purchase_id": purchase["id"],
                "provider_reference": reference,
                "project_id": project_id,
                "purchase_mode": mode,
                "payment_environment": "test",
            },
        }
        result = stripe_provider.verify_and_activate_stripe_session_data(session, database_url=str(db))
        assert result["ok"] is True
        assert result["test_mode"] is True
        status = store.entitlement_status(purchase["id"], purchase["access_token"], database_url=str(db))
        assert status["allowed"] is True
        assert status["remaining"] == expected_remaining


def test_live_session_cannot_activate_test_purchase(tmp_path, monkeypatch):
    db, _, store, _, stripe_provider, _, _ = _reload_test_app(tmp_path, monkeypatch)
    purchase = store.create_pending_purchase(
        user_email="buyer@example.com",
        project_id="mode-mismatch",
        chapter_number=2,
        chapter_title="Literature Review",
        academic_level="Bachelors",
        plan_key="bachelors_chapter",
        amount=4.99,
        currency="USD",
        display_amount=4.99,
        display_currency="USD",
        payment_provider="stripe",
        provider_reference="PRAI-ST-mode-mismatch",
        metadata={"purchase_mode": "chapter", "payment_environment": "test"},
        database_url=str(db),
    )
    result = stripe_provider.verify_and_activate_stripe_session_data(
        {
            "id": "cs_live_wrong",
            "livemode": True,
            "client_reference_id": purchase["id"],
            "amount_total": 499,
            "currency": "usd",
            "payment_status": "paid",
            "customer_email": "buyer@example.com",
            "metadata": {
                "purchase_id": purchase["id"],
                "provider_reference": purchase["provider_reference"],
                "project_id": "mode-mismatch",
                "payment_environment": "test",
            },
        },
        database_url=str(db),
    )
    assert result["ok"] is False
    assert "environment" in result["message"].lower()
