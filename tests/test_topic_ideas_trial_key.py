from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "topic-trial.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_TOPIC_IDEAS_TRIAL_KEY", "PRAI-TOPIC-TRIAL-TEST-9Q7M4K")

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
    return db, store, topic_router, main


def test_trial_key_issues_real_one_generation_entitlement(tmp_path, monkeypatch):
    db, store, topic_router, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)

    plan = client.get("/api/topic-ideas/access-plan")
    assert plan.status_code == 200
    assert plan.json()["trial"]["available"] is True
    assert plan.json()["trial"]["purchase_id_required"] is False

    invalid = client.post(
        "/api/topic-ideas/activate-trial",
        json={"email": "owner@example.com", "trial_key": "wrong-trial-key"},
    )
    assert invalid.status_code == 403

    activated = client.post(
        "/api/topic-ideas/activate-trial",
        json={
            "email": "owner@example.com",
            "trial_key": "PRAI-TOPIC-TRIAL-TEST-9Q7M4K",
        },
    )
    assert activated.status_code == 200
    credential = activated.json()
    assert credential["trial"] is True
    assert credential["purchase_id"]
    assert credential["access_token"]
    assert credential["status"]["allowed"] is True
    assert credential["status"]["remaining"]["draft"] == 1

    status = client.post(
        "/api/topic-ideas/payment-status",
        json={
            "purchase_id": credential["purchase_id"],
            "access_token": credential["access_token"],
        },
    )
    assert status.status_code == 200
    assert status.json()["allowed"] is True

    generated_payloads = []

    def fake_generation(payload):
        generated_payloads.append(dict(payload))
        return {
            "ideas": [
                {"title": f"Trial idea {index}"}
                for index in range(1, payload["max_ideas"] + 1)
            ]
        }

    monkeypatch.setattr(topic_router, "generate_topic_ideas", fake_generation)
    generated = client.post(
        "/api/topic-ideas",
        json={"research_area": "financial inclusion", "max_ideas": 12},
        headers={
            "X-ProjectReady-Purchase-ID": credential["purchase_id"],
            "X-ProjectReady-Access-Token": credential["access_token"],
            "X-Idempotency-Key": "trial-topic-generation-1",
        },
    )
    assert generated.status_code == 200
    assert generated.json()["access_tier"] == "paid_full_set"
    assert len(generated.json()["ideas"]) == 12
    assert generated_payloads[0]["max_ideas"] == 12

    used_status = client.post(
        "/api/topic-ideas/payment-status",
        json={
            "purchase_id": credential["purchase_id"],
            "access_token": credential["access_token"],
        },
    )
    assert used_status.status_code == 200
    assert used_status.json()["remaining"]["draft"] == 0


def test_trial_key_can_restore_same_email_but_not_transfer(tmp_path, monkeypatch):
    db, store, topic_router, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    payload = {
        "email": "owner@example.com",
        "trial_key": "PRAI-TOPIC-TRIAL-TEST-9Q7M4K",
    }

    first = client.post("/api/topic-ideas/activate-trial", json=payload)
    assert first.status_code == 200
    first_data = first.json()

    restored = client.post("/api/topic-ideas/activate-trial", json=payload)
    assert restored.status_code == 200
    restored_data = restored.json()
    assert restored_data["recovered"] is True
    assert restored_data["purchase_id"] == first_data["purchase_id"]
    assert restored_data["access_token"] != first_data["access_token"]

    old_token = client.post(
        "/api/topic-ideas/payment-status",
        json={
            "purchase_id": first_data["purchase_id"],
            "access_token": first_data["access_token"],
        },
    )
    assert old_token.status_code == 403

    other_email = client.post(
        "/api/topic-ideas/activate-trial",
        json={
            "email": "other@example.com",
            "trial_key": "PRAI-TOPIC-TRIAL-TEST-9Q7M4K",
        },
    )
    assert other_email.status_code == 409
