from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.claim_support_review import build_claim_support_review


def test_claim_support_review_flags_uncited_claims_and_paragraph_density():
    profile = {
        "source_bank": [
            {"authors": ["Ama Mensah"], "year": "2024", "title": "Teacher leadership", "doi": "10.1000/mensah", "citation_eligible": True},
        ]
    }
    text = (
        "# Background to the Study\n\n"
        "Teacher leadership has become an important approach to school improvement because teachers influence professional learning beyond their own classrooms. "
        "Research across school systems also shows that relational conditions shape whether teachers can exercise professional influence effectively. "
        "Trust, autonomy and collegiality can therefore affect how teacher leadership develops within schools. "
        "Existing evidence remains uneven across national settings (Mensah, 2024)."
    )
    review = build_claim_support_review(text, profile, chapter_number=1, workflow="draft")
    assert review["unsupported_claim_count"] >= 3
    assert review["under_supported_paragraph_count"] == 1
    assert review["final_output_ready"] is False
    assert all(item["status"] == "needs_source" for item in review["claims"])


def _reload(tmp_path, monkeypatch):
    db = tmp_path / "claim-support.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "0")

    import app.database as database
    import app.routers.sources as sources
    import app.routers.projects as projects
    import app.main as main

    importlib.reload(database)
    importlib.reload(projects)
    importlib.reload(sources)
    importlib.reload(main)
    database.init_db()
    return database, sources, main


def test_claim_source_search_approval_and_application_are_user_gated(tmp_path, monkeypatch):
    database, sources, main = _reload(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json={
        "title": "Teacher Leadership in Basic Schools",
        "level": "Research Masters / MPhil",
        "programme": "MPhil Education",
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }).json()
    project_id = created["id"]
    draft = (
        "# Background to the Study\n\n"
        "Teacher leadership can influence professional learning and instructional improvement across schools when teachers have meaningful opportunities to lead."
    )
    with database.get_conn() as conn:
        conn.execute("UPDATE projects SET drafts_json = ? WHERE id = ?", (json.dumps({"1": draft}), project_id))
        conn.commit()

    review_response = client.get(f"/api/projects/{project_id}/claim-support-review?workflow=draft&chapter_number=1")
    assert review_response.status_code == 200
    review = review_response.json()["review"]
    assert review["unsupported_claim_count"] == 1
    claim_id = review["claims"][0]["id"]

    candidate = {
        "title": "Teacher leadership and professional learning",
        "authors": ["Ama Mensah"],
        "year": "2025",
        "source": "Journal of Educational Leadership",
        "doi": "10.1000/tl.2025.1",
        "url": "https://doi.org/10.1000/tl.2025.1",
        "abstract": "The study found that teacher leadership was positively associated with professional learning and instructional improvement in schools.",
        "database": "OpenAlex",
        "metadata_verified": True,
        "citation_eligible": True,
        "claim_support_eligible": True,
        "relevance_tier": "highly_relevant",
        "relevance_reason": "Direct conceptual and outcome match.",
    }

    monkeypatch.setattr(sources, "search_literature_sources", lambda **kwargs: {
        "sources": [candidate], "provider_errors": [], "databases": ["OpenAlex"]
    })
    found = client.post(f"/api/projects/{project_id}/claim-support/find-sources", json={
        "workflow": "draft", "chapter_number": 1, "claim_id": claim_id, "max_results": 12,
    })
    assert found.status_code == 200
    candidate_id = found.json()["candidates"][0]["candidate_id"]

    rejected = client.post(f"/api/projects/{project_id}/claim-support/approve", json={
        "workflow": "draft", "chapter_number": 1, "claim_id": claim_id,
        "candidate_id": candidate_id, "confirm_claim_support": False,
    })
    assert rejected.status_code == 422

    approved = client.post(f"/api/projects/{project_id}/claim-support/approve", json={
        "workflow": "draft", "chapter_number": 1, "claim_id": claim_id,
        "candidate_id": candidate_id, "confirm_claim_support": True,
    })
    assert approved.status_code == 200

    applied = client.post(f"/api/projects/{project_id}/claim-support/apply-approved", json={
        "workflow": "draft", "chapter_number": 1, "citation_style": "APA 7th",
    })
    assert applied.status_code == 200
    body = applied.json()
    assert "(Mensah, 2025)" in body["text"]
    assert body["review"]["unsupported_claim_count"] == 0
    assert body["review"]["final_output_ready"] is True


def test_preoutput_claim_review_ui_exists_in_both_workflows():
    workspace = Path("app/static/workspace.html").read_text(encoding="utf-8")
    workspace_js = Path("app/static/app.js").read_text(encoding="utf-8")
    strengthener = Path("app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    strengthener_js = Path("app/static/chapter_strengthener.js").read_text(encoding="utf-8")

    assert 'id="claimSupportReviewPanel"' in workspace
    assert "Find verified sources" in workspace_js
    assert "claim-support/apply-approved" in workspace_js
    assert 'id="strengthenerClaimSupportPanel"' in strengthener
    assert "Find verified sources" in strengthener_js
    assert "claim-support/apply-approved" in strengthener_js


def test_legacy_draft_is_audited_at_export_and_evidence_claims_are_blocked(tmp_path, monkeypatch):
    database, _, main = _reload(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json={
        "title": "Teacher Leadership in Basic Schools",
        "level": "Research Masters / MPhil",
        "programme": "MPhil Education",
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }).json()
    project_id = created["id"]
    draft = (
        "# Background to the Study\n\n"
        "Teacher leadership improves professional learning across school systems because teachers can influence colleagues beyond their own classrooms and support instructional change."
    )
    with database.get_conn() as conn:
        conn.execute("UPDATE projects SET drafts_json = ? WHERE id = ?", (json.dumps({"1": draft}), project_id))
        conn.commit()

    response = client.get(f"/api/projects/{project_id}/export/chapter/1")
    assert response.status_code == 409
    assert "Claim Support Review" in str(response.json().get("detail")) or "highlighted unsupported claims" in str(response.json().get("detail"))

    with database.get_conn() as conn:
        row = conn.execute("SELECT profile_json FROM projects WHERE id = ?", (project_id,)).fetchone()
    profile = json.loads(dict(row)["profile_json"])
    review = profile["claim_support_reviews"]["draft:1"]
    assert review["unsupported_claim_count"] >= 1
    assert review["final_output_ready"] is False


def test_legacy_citation_light_draft_can_pass_lazy_preoutput_audit(tmp_path, monkeypatch):
    database, _, main = _reload(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json={
        "title": "Teacher Leadership in Basic Schools",
        "level": "Research Masters / MPhil",
        "programme": "MPhil Education",
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }).json()
    project_id = created["id"]
    with database.get_conn() as conn:
        conn.execute(
            "UPDATE projects SET drafts_json = ? WHERE id = ?",
            (json.dumps({"1": "# Research Objectives\n\n1. Examine teacher leadership in selected schools."}), project_id),
        )
        conn.commit()

    response = client.get(f"/api/projects/{project_id}/export/project-working-file")
    assert response.status_code == 200
