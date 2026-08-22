from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.citation_matrix import remove_unverified_generated_citations
from app.selected_papers import MAX_SELECTED_PAPERS, build_selected_paper_record, prompt_selected_papers


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "selected-papers.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "0")

    import app.database as database
    import app.routers.projects as projects
    import app.routers.sources as sources
    import app.routers.chapter_strengthener as chapter_strengthener
    import app.main as main

    importlib.reload(database)
    importlib.reload(projects)
    importlib.reload(sources)
    importlib.reload(chapter_strengthener)
    importlib.reload(main)
    database.init_db()
    return database, main


def _project_payload():
    return {
        "title": "Digital Procurement and Transparency",
        "programme": "MPhil Procurement",
        "level": "Research Masters (e.g. MPhil)",
        "research_area": "procurement transparency",
        "study_context": "Public institutions in Ghana",
        "research_approach": "Quantitative",
        "objectives": ["Examine the effect of digital procurement on transparency"],
        "research_questions": ["How does digital procurement affect transparency?"],
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }


def _paper_text():
    return (
        "Digital Procurement and Transparency in Public Institutions\n"
        "A research article supplied by the student.\n\n"
        "Abstract\nDigital procurement systems may improve information disclosure and auditability. "
        "The study discusses transparency mechanisms and institutional implementation.\n\n"
        "Methods\nThe research used a cross-sectional survey.\n\n"
        "Results\nThe findings are discussed without a DOI in this test paper.\n\n"
        "Conclusion\nDigital procurement should be assessed together with organisational capacity."
    )


def test_selected_paper_limit_and_unverified_record_fail_closed():
    assert MAX_SELECTED_PAPERS == 50
    record = build_selected_paper_record("student-paper.txt", _paper_text().encode())
    assert record["user_uploaded_full_text"] is True
    assert record["citation_eligible"] is False
    assert record["metadata_status"] == "needs_user_confirmation"
    assert "Digital Procurement" in record["evidence_excerpt"]


def test_workspace_upload_confirm_and_delete_selected_paper(tmp_path, monkeypatch):
    database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    project_id = client.post("/api/projects", json=_project_payload()).json()["id"]

    uploaded = client.post(
        f"/api/projects/{project_id}/selected-papers",
        files=[("files", ("student-paper.txt", _paper_text().encode(), "text/plain"))],
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["count"] == 1
    assert body["citation_ready"] == 0
    paper = body["papers"][0]
    assert paper["citation_eligible"] is False

    confirmed = client.patch(
        f"/api/projects/{project_id}/selected-papers/{paper['id']}",
        json={
            "title": "Digital Procurement and Transparency in Public Institutions",
            "authors": "Ama Mensah; Kojo Boateng",
            "year": "2025",
            "source": "Journal of Public Procurement Research",
            "doi": "",
            "url": "",
            "confirm": True,
        },
    )
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body["paper"]["citation_eligible"] is True
    assert confirmed_body["paper"]["metadata_status"] == "confirmed_by_user"
    assert confirmed_body["source_bank"][0]["attachment_origin"] == "uploaded_selected_paper"
    assert "evidence_excerpt" not in confirmed_body["source_bank"][0]

    # Public project retrieval keeps the UI lightweight, while the database keeps
    # the extracted evidence for generation.
    project_view = client.get(f"/api/projects/{project_id}").json()
    assert "evidence_excerpt" not in project_view["profile"]["selected_papers"][0]
    with database.get_conn() as conn:
        row = conn.execute("SELECT profile_json FROM projects WHERE id = ?", (project_id,)).fetchone()
    raw_profile = json.loads(row[0])
    assert raw_profile["selected_papers"][0]["evidence_excerpt"]
    assert raw_profile["source_bank"][0]["evidence_excerpt"] == ""
    assert raw_profile["source_bank"][0]["abstract"]

    guarded, audit = remove_unverified_generated_citations(
        "Evidence is available (Mensah, 2025).\n\n# References\nInvented reference.",
        raw_profile,
    )
    assert "(Mensah, 2025)" in guarded
    assert audit["removed_unverified_count"] == 0
    assert "Digital Procurement and Transparency" in guarded

    deleted = client.delete(f"/api/projects/{project_id}/selected-papers/{paper['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["count"] == 0


def test_strengthener_can_extract_selected_papers_before_project_creation(tmp_path, monkeypatch):
    _database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    response = client.post(
        "/api/chapter-strengthener/extract-selected-papers",
        files=[("files", ("chosen-paper.txt", _paper_text().encode(), "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["papers"][0]["citation_eligible"] is False
    assert body["papers"][0]["evidence_excerpt"]


def test_both_student_workflows_expose_fifty_paper_library():
    workspace = Path("app/static/workspace.html").read_text(encoding="utf-8")
    workspace_js = Path("app/static/app.js").read_text(encoding="utf-8")
    strengthener = Path("app/static/chapter_strengthener.html").read_text(encoding="utf-8")
    strengthener_js = Path("app/static/chapter_strengthener.js").read_text(encoding="utf-8")

    assert 'id="selectedPaperFiles"' in workspace and "multiple" in workspace
    assert "up to <strong>50 papers</strong>" in workspace
    assert "/selected-papers" in workspace_js
    assert 'id="strengthenerSelectedPaperFiles"' in strengthener and "multiple" in strengthener
    assert "up to <strong>50 papers</strong>" in strengthener
    assert "/api/chapter-strengthener/extract-selected-papers" in strengthener_js
    assert "selected_papers: strengthenerSelectedPapers" in strengthener_js


def test_all_fifty_papers_influence_compact_map_without_fifty_long_excerpts():
    papers = []
    for i in range(50):
        papers.append({
            "id": f"p{i}",
            "filename": f"paper-{i}.txt",
            "title": f"Employee motivation and performance study {i}",
            "authors": [f"Author {i}"],
            "year": "2025",
            "source": "Test Journal",
            "citation_eligible": True,
            "metadata_verified": True,
            "evidence_capsule": f"Results: motivation and performance evidence from paper {i}. Topics: motivation, performance, employees",
            "evidence_excerpt": (f"Paper {i} reports evidence about employee motivation and task performance. " * 120),
        })
    context = prompt_selected_papers({
        "title": "Employee Motivation and Task Performance",
        "research_area": "human resource management",
        "study_context": "public sector",
        "objectives": ["Examine employee motivation and task performance"],
        "selected_papers": papers,
    }, 2)
    assert context["count"] == 50
    assert context["library_map_count"] == 50
    assert len(context["library_map"]) == 50
    assert len(context["papers"]) <= 8
    assert all(len(item["evidence_excerpt"]) <= 1400 for item in context["papers"])
