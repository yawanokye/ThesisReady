from __future__ import annotations

import importlib
from pathlib import Path


def _reload_job_store(monkeypatch, db_path: Path):
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.delenv("PROJECTREADY_SQLITE_DB_PATH", raising=False)
    import app.database as database
    import app.jobs.store as store
    importlib.reload(database)
    importlib.reload(store)
    database.init_db()
    store.init_job_tables()
    return store


def test_durable_job_lifecycle_and_private_token(monkeypatch, tmp_path):
    store = _reload_job_store(monkeypatch, tmp_path / "jobs.db")
    job, token = store.create_job(
        job_type="chapter_draft",
        payload={"project_id": "project-1", "request": {"chapter_number": 2}},
        project_id="project-1",
        chapter_number=2,
        max_attempts=2,
    )
    assert job["status"] == "queued"
    assert store.verify_job_token(job["id"], token) is True
    assert store.verify_job_token(job["id"], "wrong-token") is False

    claimed = store.claim_next_job(worker_id="worker-test", lease_seconds=600)
    assert claimed and claimed["id"] == job["id"]
    assert claimed["status"] == "running"

    store.update_job(job["id"], progress=55, stage="generating", message="Drafting section 2.")
    updated = store.get_job(job["id"])
    assert updated["progress"] == 55
    assert updated["stage"] == "generating"

    store.complete_job(job["id"], {"draft": "Completed chapter"})
    complete = store.get_job(job["id"])
    assert complete["status"] == "completed"
    assert complete["result"]["draft"] == "Completed chapter"


def test_failed_job_retries_then_stops(monkeypatch, tmp_path):
    store = _reload_job_store(monkeypatch, tmp_path / "retry.db")
    job, _token = store.create_job(
        job_type="chapter_strengthener",
        payload={"project_id": "project-2"},
        project_id="project-2",
        chapter_number=1,
        max_attempts=2,
    )
    first = store.claim_next_job(worker_id="worker-a", lease_seconds=600)
    assert first["attempts"] == 1
    retry = store.fail_or_retry_job(job["id"], "temporary timeout")
    assert retry["status"] == "retrying"
    # Make the retry immediately available for the test.
    from app.database import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE projectready_jobs SET available_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", job["id"]))
        conn.commit()
    second = store.claim_next_job(worker_id="worker-b", lease_seconds=600)
    assert second["attempts"] == 2
    failed = store.fail_or_retry_job(job["id"], "second timeout")
    assert failed["status"] == "failed"


def test_exhausted_interrupted_job_is_failed_not_requeued(monkeypatch, tmp_path):
    store = _reload_job_store(monkeypatch, tmp_path / "exhausted.db")
    job, _token = store.create_job(
        job_type="chapter_draft",
        payload={"_preauthorized_claim": {"claimed": False}},
        project_id="project-3",
        chapter_number=3,
        max_attempts=1,
    )
    claimed = store.claim_next_job(worker_id="worker-crash", lease_seconds=600)
    assert claimed["attempts"] == 1
    from app.database import get_conn
    with get_conn() as conn:
        conn.execute(
            "UPDATE projectready_jobs SET lease_expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", job["id"]),
        )
        conn.commit()
    exhausted = store.fail_exhausted_stale_jobs()
    assert [item["id"] for item in exhausted] == [job["id"]]
    assert store.get_job(job["id"])["status"] == "failed"
    assert store.claim_next_job(worker_id="worker-new", lease_seconds=600) is None
