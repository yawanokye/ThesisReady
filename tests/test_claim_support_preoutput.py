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


def test_legacy_draft_is_audited_at_export_without_claim_review_block(tmp_path, monkeypatch):
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

    import app.access_control as access
    access.set_access_policy("temporary_open", open_hours=1, updated_by="test")
    response = client.get(f"/api/projects/{project_id}/export/chapter/1")
    assert response.status_code == 200
    assert response.headers.get("X-ProjectReady-Evidence-Review") == "pending"

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


def test_approval_removes_placeholder_and_final_summary_counts_verified_references(tmp_path, monkeypatch):
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
        "Research evidence indicates that teacher leadership can influence professional learning across schools "
        "[insert verified source for the unsupported citation removed here]."
    )
    with database.get_conn() as conn:
        conn.execute("UPDATE projects SET drafts_json = ? WHERE id = ?", (json.dumps({"1": draft}), project_id))
        conn.commit()

    review = client.get(f"/api/projects/{project_id}/claim-support-review?workflow=draft&chapter_number=1").json()["review"]
    claim_id = review["claims"][0]["id"]
    candidates = [
        {
            "title": "Teacher leadership and professional learning A",
            "authors": ["Ama Mensah"], "year": "2025", "source": "Journal A",
            "doi": "10.1000/a", "url": "https://doi.org/10.1000/a",
            "abstract": "Teacher leadership was positively associated with professional learning across schools.",
            "database": "OpenAlex", "metadata_verified": True, "citation_eligible": True,
            "claim_support_eligible": True, "relevance_tier": "highly_relevant",
        },
        {
            "title": "Teacher leadership and professional learning B",
            "authors": ["Kwame Boateng"], "year": "2024", "source": "Journal B",
            "doi": "10.1000/b", "url": "https://doi.org/10.1000/b",
            "abstract": "The study reports a relationship between teacher leadership and professional learning.",
            "database": "ERIC", "metadata_verified": True, "citation_eligible": True,
            "claim_support_eligible": True, "relevance_tier": "highly_relevant",
        },
    ]
    monkeypatch.setattr(sources, "search_literature_sources", lambda **kwargs: {
        "sources": candidates, "provider_errors": [],
        "databases": ["OpenAlex", "Crossref", "Semantic Scholar", "ERIC", "DataCite", "Europe PMC", "PubMed"],
        "external_searches": [{"provider": "Google Scholar", "url": "https://scholar.google.com/scholar?q=teacher+leadership"}],
    })
    found = client.post(f"/api/projects/{project_id}/claim-support/find-sources", json={
        "workflow": "draft", "chapter_number": 1, "claim_id": claim_id, "max_results": 16,
    }).json()
    assert len(found["candidates"]) == 2
    assert found["external_searches"][0]["provider"] == "Google Scholar"

    for candidate in found["candidates"]:
        approved = client.post(f"/api/projects/{project_id}/claim-support/approve", json={
            "workflow": "draft", "chapter_number": 1, "claim_id": claim_id,
            "candidate_id": candidate["candidate_id"], "confirm_claim_support": True,
        })
        assert approved.status_code == 200
        assert "insert verified source" not in approved.json()["text"].lower()

    applied = client.post(f"/api/projects/{project_id}/claim-support/apply-approved", json={
        "workflow": "draft", "chapter_number": 1, "citation_style": "APA 7th",
    })
    assert applied.status_code == 200
    body = applied.json()
    summary = body["review"]["final_approval_summary"]
    assert summary["verified_citation_references_added"] == 2
    assert summary["unique_verified_sources_added"] == 2
    assert "Mensah, 2025" in body["text"]
    assert "Boateng, 2024" in body["text"]
    assert "insert verified source" not in body["text"].lower()


def test_ignore_removes_placeholder_and_persists_across_reaudit(tmp_path, monkeypatch):
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
        "Research evidence indicates that teacher leadership can influence professional learning across schools "
        "[insert verified source for the unsupported citation removed here]."
    )
    with database.get_conn() as conn:
        conn.execute("UPDATE projects SET drafts_json = ? WHERE id = ?", (json.dumps({"1": draft}), project_id))
        conn.commit()
    review = client.get(f"/api/projects/{project_id}/claim-support-review?workflow=draft&chapter_number=1").json()["review"]
    claim_id = review["claims"][0]["id"]
    ignored = client.post(f"/api/projects/{project_id}/claim-support/ignore", json={
        "workflow": "draft", "chapter_number": 1, "claim_id": claim_id,
    })
    assert ignored.status_code == 200
    assert "insert verified source" not in ignored.json()["text"].lower()
    refreshed = client.get(f"/api/projects/{project_id}/claim-support-review?workflow=draft&chapter_number=1").json()["review"]
    assert all(item["id"] != claim_id for item in refreshed["claims"])
    assert refreshed["ignored_item_count"] >= 1


def test_claim_support_ui_has_progress_ignore_and_final_approval_counts():
    workspace_js = Path("app/static/app.js").read_text(encoding="utf-8")
    strengthener_js = Path("app/static/chapter_strengthener.js").read_text(encoding="utf-8")
    for js in (workspace_js, strengthener_js):
        assert "Searching OpenAlex, Crossref, Semantic Scholar, ERIC, DataCite, Europe PMC and PubMed" in js
        assert "Ignore" in js
        assert "ignore-bulk" in js
        assert "verified citation reference(s) added" in js
        assert "Google Scholar" in js


def test_bulk_ignore_removes_multiple_review_items_once(tmp_path, monkeypatch):
    database, _sources, main = _reload(tmp_path, monkeypatch)
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
        "Research shows that teacher leadership improves professional learning [insert verified source for the unsupported citation removed here]. "
        "Studies also indicate that professional trust is associated with teachers' willingness to lead [insert verified source for the unsupported citation removed here]."
    )
    with database.get_conn() as conn:
        conn.execute("UPDATE projects SET drafts_json = ? WHERE id = ?", (json.dumps({"1": draft}), project_id))
        conn.commit()
    review = client.get(f"/api/projects/{project_id}/claim-support-review?workflow=draft&chapter_number=1").json()["review"]
    ids = [item["id"] for item in review["claims"][:2]]
    assert len(ids) == 2
    response = client.post(f"/api/projects/{project_id}/claim-support/ignore-bulk", json={
        "workflow": "draft", "chapter_number": 1, "claim_ids": ids,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["ignored_count"] == 2
    assert "insert verified source" not in body["text"].lower()
    remaining_ids = {item["id"] for item in body["review"]["claims"]}
    assert not remaining_ids.intersection(ids)
