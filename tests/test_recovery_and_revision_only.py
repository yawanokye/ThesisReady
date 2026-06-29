from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import database
from app.payments import store as payment_store
from app.payments.entitlements import (
    build_plans_payload,
    plan_key_for_level,
    quota_payload,
)
from app.project_recovery import recover_projects, set_project_recovery
from app.routers.chapter_strengthener import create_external_revision_project
from app.schemas import ExternalRevisionProjectCreate


@pytest.fixture()
def isolated_databases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_db = tmp_path / "projectready.db"
    payment_db = tmp_path / "payments.db"
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "SQLITE_DB_PATH", project_db)
    monkeypatch.setattr(payment_store, "DATABASE_URL", "")
    monkeypatch.setattr(payment_store, "SQLITE_PAYMENT_DB", str(payment_db))
    database.init_db()
    payment_store.init_payment_tables("")
    return project_db, payment_db


def test_project_recovery_with_email_and_pin(isolated_databases):
    with database.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, title, profile_json, selected_sections_json, drafts_json, checks_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "project-one",
                "Procurement literacy thesis",
                json.dumps({"level": "Research Masters / MPhil"}),
                "{}",
                "{}",
                "{}",
            ),
        )
        conn.commit()

    set_project_recovery("project-one", "student@example.com", "123456")
    recovered = recover_projects("Student@Example.com", "123456")
    assert len(recovered) == 1
    assert recovered[0]["id"] == "project-one"
    assert recover_projects("student@example.com", "654321") == []


def test_revision_only_plan_has_no_draft_credit():
    assert plan_key_for_level("Research Masters / MPhil", "revision_only") == "masters_revision"
    quotas = quota_payload("masters_revision")
    assert quotas == {
        "drafts_total": 0,
        "revisions_total": 1,
        "compliance_total": 1,
        "exports_total": 1,
    }
    payload = build_plans_payload("Research Masters / MPhil", "revision_only")
    recommended = next(plan for plan in payload["paid_plans"] if plan["recommended"])
    assert recommended["includes"]["initial_draft"] == 0
    assert recommended["includes"]["revision"] == 1


def test_external_revision_project_is_created_and_recoverable(isolated_databases):
    result = create_external_revision_project(
        ExternalRevisionProjectCreate(
            thesis_title="Digital procurement and public value",
            chapter_type="2. Literature Review",
            chapter_text="Existing literature discusses digital procurement and public value. " * 4,
            academic_level="Research Masters / MPhil",
            research_area="Digital procurement",
            context="Ghana",
            objectives="To examine digital procurement and public value.",
            recovery_email="student@example.com",
            recovery_pin="246810",
            include_source_search=False,
            academic_integrity_confirmed=True,
            user_contribution_confirmed=True,
        )
    )
    assert result["purchase_mode"] == "revision_only"
    assert result["profile"]["project_kind"] == "external_revision"
    recovered = recover_projects("student@example.com", "246810")
    assert recovered[0]["id"] == result["id"]


def test_revision_only_purchase_rejects_draft_but_allows_revision(isolated_databases):
    purchase = payment_store.create_pending_purchase(
        user_email="student@example.com",
        project_id="external-project",
        chapter_number=2,
        chapter_title="Literature Review",
        academic_level="Research Masters / MPhil",
        plan_key="masters_revision",
        amount=5.99,
        currency="USD",
        display_amount=5.99,
        display_currency="USD",
        payment_provider="stripe",
        provider_reference="PRAI-ST-revision-only",
        metadata={"purchase_mode": "revision_only"},
        database_url="",
    )
    payment_store.activate_purchase(
        provider_reference=purchase["provider_reference"],
        verified_amount=5.99,
        verified_currency="USD",
        database_url="",
    )
    with pytest.raises(PermissionError):
        payment_store.claim_entitlement(
            purchase_id=purchase["id"],
            access_token=purchase["access_token"],
            project_id="external-project",
            chapter_number=2,
            chapter_title="Literature Review",
            action="draft",
            idempotency_key="no-draft",
            database_url="",
        )
    claim = payment_store.claim_entitlement(
        purchase_id=purchase["id"],
        access_token=purchase["access_token"],
        project_id="external-project",
        chapter_number=2,
        chapter_title="Literature Review",
        action="revision",
        idempotency_key="revision-one",
        database_url="",
    )
    assert claim["claimed"] is True


def test_recovery_rotates_active_purchase_token(isolated_databases):
    purchase = payment_store.create_pending_purchase(
        user_email="student@example.com",
        project_id="recoverable-project",
        chapter_number=1,
        chapter_title="Introduction",
        academic_level="Bachelors",
        plan_key="bachelors_chapter",
        amount=4.99,
        currency="USD",
        display_amount=4.99,
        display_currency="USD",
        payment_provider="stripe",
        provider_reference="PRAI-ST-recovery-token",
        metadata={},
        database_url="",
    )
    payment_store.activate_purchase(
        provider_reference=purchase["provider_reference"],
        verified_amount=4.99,
        verified_currency="USD",
        database_url="",
    )
    renewed = payment_store.rotate_project_access_tokens("recoverable-project", database_url="")
    assert len(renewed) == 1
    assert renewed[0]["purchase_id"] == purchase["id"]
    assert renewed[0]["access_token"] != purchase["access_token"]
    assert payment_store.verify_access_token(
        purchase["id"], renewed[0]["access_token"], database_url=""
    )
    assert not payment_store.verify_access_token(
        purchase["id"], purchase["access_token"], database_url=""
    )
