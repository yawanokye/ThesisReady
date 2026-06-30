from __future__ import annotations

import importlib
from fastapi.testclient import TestClient


def _reload(tmp_path, monkeypatch):
    db = tmp_path / "all-recovery.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_SUPPORT_RECOVERY_KEY", "support-recovery-test-key-12345")
    monkeypatch.setenv("APP_BASE_URL", "https://projectreadyai.com")

    import app.database as database
    import app.payments.store as store
    import app.routers.payments as payments
    import app.main as main

    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(payments)
    importlib.reload(main)
    return db, store, main


def _paid_purchase(store, db, *, email="buyer@example.com", plan_key="bachelors_chapter", mode="chapter"):
    chapter_number = 99 if plan_key == "topic_ideas_access" else 1
    purchase = store.create_pending_purchase(
        user_email=email,
        project_id="topic-access" if chapter_number == 99 else "project-123",
        chapter_number=chapter_number,
        chapter_title="Topic Ideas Access" if chapter_number == 99 else "Introduction",
        academic_level="Topic Ideas" if chapter_number == 99 else "Bachelors",
        plan_key=plan_key,
        amount=1.50 if plan_key == "topic_ideas_access" else 4.99,
        currency="USD",
        display_amount=1.50 if plan_key == "topic_ideas_access" else 4.99,
        display_currency="USD",
        payment_provider="stripe",
        provider_reference=f"PRAI-ST-{plan_key}",
        metadata={"purchase_mode": mode, "return_path": "/topic-ideas" if chapter_number == 99 else "/workspace"},
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


def test_support_can_search_by_email_without_purchase_id(tmp_path, monkeypatch):
    db, store, main = _reload(tmp_path, monkeypatch)
    topic = _paid_purchase(store, db, plan_key="topic_ideas_access", mode="topic_ideas")
    chapter = _paid_purchase(store, db, plan_key="bachelors_chapter", mode="chapter")
    client = TestClient(main.app)
    response = client.post("/api/admin/payment-recovery/search", json={
        "support_key": "support-recovery-test-key-12345",
        "email": "buyer@example.com",
        "payment_identifier": "",
    })
    assert response.status_code == 200
    ids = {item["purchase_id"] for item in response.json()["purchases"]}
    assert ids == {topic["id"], chapter["id"]}
    assert all("access_token" not in item for item in response.json()["purchases"])


def test_wrong_support_key_is_rejected(tmp_path, monkeypatch):
    db, store, main = _reload(tmp_path, monkeypatch)
    _paid_purchase(store, db)
    client = TestClient(main.app)
    response = client.post("/api/admin/payment-recovery/search", json={
        "support_key": "incorrect-key-value",
        "email": "buyer@example.com",
    })
    assert response.status_code == 403


def test_support_link_redeems_once_for_topic_ideas(tmp_path, monkeypatch):
    db, store, main = _reload(tmp_path, monkeypatch)
    purchase = _paid_purchase(store, db, plan_key="topic_ideas_access", mode="topic_ideas")
    client = TestClient(main.app)
    created = client.post("/api/admin/payment-recovery/create-link", json={
        "support_key": "support-recovery-test-key-12345",
        "email": "buyer@example.com",
        "purchase_id": purchase["id"],
        "operator_note": "Customer reported locked options",
    })
    assert created.status_code == 200
    recovery_url = created.json()["recovery_url"]
    handoff = recovery_url.split("handoff=", 1)[1]

    redeemed = client.post("/api/payments/redeem-recovery", json={"handoff": handoff})
    assert redeemed.status_code == 200
    data = redeemed.json()
    assert data["product_area"] == "topic_ideas"
    assert data["access_token"]

    repeated = client.post("/api/payments/redeem-recovery", json={"handoff": handoff})
    assert repeated.status_code == 403


def test_support_link_redeems_for_thesis_workspace(tmp_path, monkeypatch):
    db, store, main = _reload(tmp_path, monkeypatch)
    purchase = _paid_purchase(store, db, plan_key="bachelors_chapter", mode="chapter")
    client = TestClient(main.app)
    created = client.post("/api/admin/payment-recovery/create-link", json={
        "support_key": "support-recovery-test-key-12345",
        "email": "buyer@example.com",
        "purchase_id": purchase["id"],
    })
    handoff = created.json()["recovery_url"].split("handoff=", 1)[1]
    redeemed = client.post("/api/payments/redeem-recovery", json={"handoff": handoff})
    assert redeemed.status_code == 200
    assert redeemed.json()["product_area"] == "thesis_workspace"
    assert redeemed.json()["project_id"] == "project-123"
