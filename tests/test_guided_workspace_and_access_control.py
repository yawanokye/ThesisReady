from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _use_temp_db(monkeypatch, tmp_path):
    import app.database as database
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "SQLITE_DB_PATH", tmp_path / "guided-access.db")


def test_access_policy_supports_commercial_open_and_payment_required(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    import app.access_control as access

    commercial = access.set_access_policy("commercial", updated_by="test")
    assert commercial["mode"] == "commercial"
    assert commercial["free_starter_enabled"] is True

    opened = access.set_access_policy("temporary_open", open_hours=2, updated_by="test")
    assert opened["temporary_open"] is True
    assert opened["open_until"]
    assert access.public_access_status("thesis_workspace")["temporary_open"] is True

    locked = access.set_access_policy("payment_required", updated_by="test")
    assert locked["payment_required"] is True
    assert locked["free_starter_enabled"] is False


def test_complimentary_token_is_page_limited_scoped_and_case_insensitive(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    import app.access_control as access

    issued = access.issue_complimentary_token(
        page_limit=12,
        label="Pilot student",
        assigned_email="student@example.com",
        product_area="thesis_workspace",
        validity_days=10,
        created_by="test",
    )
    token = issued["token"]
    status = access.validate_complimentary_token(
        token.lower(),
        product_area="thesis_workspace",
        supplied_email="student@example.com",
    )
    assert status["pages_remaining"] == 12

    reservation = access.reserve_complimentary_for_background(
        raw_token=token,
        supplied_email="student@example.com",
        product_area="thesis_workspace",
        project_id="project-1",
        chapter_number=2,
        action="draft",
        requested_pages=7,
        idempotency_key="test-reservation-1",
    )
    assert reservation["reserved_pages"] == 7
    assert access.complimentary_status(token, product_area="thesis_workspace", supplied_email="student@example.com")["pages_remaining"] == 5

    access.rollback_complimentary_usage(reservation["complimentary_usage_id"])
    assert access.complimentary_status(token, product_area="thesis_workspace", supplied_email="student@example.com")["pages_remaining"] == 12

    with pytest.raises(PermissionError):
        access.validate_complimentary_token(token, product_area="chapter_strengthener", supplied_email="student@example.com")
    with pytest.raises(PermissionError):
        access.validate_complimentary_token(token, product_area="thesis_workspace", supplied_email="other@example.com")
    with pytest.raises(PermissionError):
        access.validate_complimentary_token(token, product_area="thesis_workspace", supplied_email="student@example.com", require_pages=13)


def test_workspace_and_strengthener_use_standalone_forms_with_left_guidance():
    workspace = (ROOT / "app/static/workspace.html").read_text(encoding="utf-8")
    strengthener = (ROOT / "app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/guided-workspace.css").read_text(encoding="utf-8")

    assert 'id="workspaceFlowSidebar"' in workspace
    assert "Standalone chapter generation form" in workspace
    assert 'id="workspaceComplimentaryToken"' in workspace
    assert 'data-flow-step="generate"' in workspace

    assert 'id="strengthenerFlowSidebar"' in strengthener
    assert "Standalone chapter strengthening form" in strengthener
    assert 'id="strengthenerComplimentaryToken"' in strengthener
    assert 'id="strengthenerOptionalSupport"' in strengthener
    assert 'data-flow-step="review"' in strengthener
    assert "position:sticky" in css


def test_restricted_developer_portal_contains_access_and_complimentary_controls():
    html = (ROOT / "app/internal_assets/portal.html").read_text(encoding="utf-8")
    js = (ROOT / "app/internal_assets/portal.js").read_text(encoding="utf-8")

    assert "Research workspace access mode" in html
    assert 'value="commercial"' in html
    assert 'value="temporary_open"' in html
    assert 'value="payment_required"' in html
    assert 'id="complimentaryTokenForm"' in html
    assert 'id="complimentaryPages"' in html
    assert "createComplimentaryToken" in js
    assert "complimentary-tokens/${token.id}/revoke" in js
