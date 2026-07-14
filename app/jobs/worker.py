from __future__ import annotations

import os
import socket
import threading
import time
import traceback
from contextlib import contextmanager
from typing import Any, Iterator

from app.database import init_db
from app.jobs.handlers import PermanentJobError, process_job
from app.jobs.store import (
    claim_next_job,
    complete_job,
    fail_or_retry_job,
    fail_exhausted_stale_jobs,
    get_job,
    init_job_tables,
    renew_lease,
    update_job,
)
from app.payments.store import complete_claim, init_payment_tables, rollback_claim

POLL_SECONDS = max(1.0, float(os.getenv("PROJECTREADY_WORKER_POLL_SECONDS", "2") or 2))
LEASE_SECONDS = max(600, int(os.getenv("PROJECTREADY_WORKER_LEASE_SECONDS", "2700") or 2700))
HEARTBEAT_SECONDS = max(30, min(300, int(os.getenv("PROJECTREADY_WORKER_HEARTBEAT_SECONDS", "90") or 90)))
WORKER_ID = str(os.getenv("PROJECTREADY_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}")


def _claim(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    return payload.get("_preauthorized_claim") or {}


def _complete_entitlement(job: dict[str, Any]) -> None:
    claim = _claim(job)
    usage_id = str(claim.get("usage_id") or "")
    if usage_id and claim.get("claimed"):
        complete_claim(usage_id)


def _rollback_entitlement(job: dict[str, Any]) -> None:
    claim = _claim(job)
    usage_id = str(claim.get("usage_id") or "")
    if usage_id and claim.get("claimed"):
        rollback_claim(usage_id)


@contextmanager
def _heartbeat(job_id: str) -> Iterator[None]:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                renew_lease(job_id, worker_id=WORKER_ID, lease_seconds=LEASE_SECONDS)
            except Exception:
                traceback.print_exc()

    thread = threading.Thread(target=run, name=f"job-heartbeat-{job_id[:8]}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)


def run_once() -> bool:
    for exhausted in fail_exhausted_stale_jobs():
        _rollback_entitlement(exhausted)
        print(f"[worker {WORKER_ID}] failed exhausted interrupted job {exhausted.get('id')}", flush=True)
    job = claim_next_job(worker_id=WORKER_ID, lease_seconds=LEASE_SECONDS)
    if not job:
        return False

    job_id = str(job.get("id") or "")
    print(f"[worker {WORKER_ID}] processing {job_id} ({job.get('job_type')})", flush=True)

    def progress(value: int, stage: str, message: str) -> None:
        update_job(job_id, progress=value, stage=stage, message=message)

    try:
        with _heartbeat(job_id):
            result = process_job(job, progress)
        _complete_entitlement(job)
        complete_job(job_id, result)
        print(f"[worker {WORKER_ID}] completed {job_id}", flush=True)
    except PermanentJobError as exc:
        final = fail_or_retry_job(job_id, str(exc), permanent=True)
        _rollback_entitlement(job)
        print(f"[worker {WORKER_ID}] permanently failed {job_id}: {exc}", flush=True)
    except Exception as exc:
        traceback.print_exc()
        final = fail_or_retry_job(job_id, str(exc), permanent=False)
        if final and str(final.get("status")) == "failed":
            _rollback_entitlement(job)
        print(f"[worker {WORKER_ID}] attempt failed {job_id}: {exc}", flush=True)
    return True


def main() -> None:
    init_db()
    init_payment_tables()
    init_job_tables()
    print(
        f"ProjectReady background worker started: id={WORKER_ID}, poll={POLL_SECONDS}s, lease={LEASE_SECONDS}s",
        flush=True,
    )
    while True:
        processed = run_once()
        if not processed:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
