from __future__ import annotations

import importlib
import json
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "flagship-projectready.db"
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "0")

    import app.database as database
    import app.routers.projects as projects
    import app.routers.generation as generation
    import app.main as main

    importlib.reload(database)
    importlib.reload(projects)
    importlib.reload(generation)
    importlib.reload(main)
    database.init_db()
    return db, database, main


def _project_payload():
    return {
        "title": "Digital Procurement and Transparency in Public Institutions",
        "level": "Research Masters (e.g. MPhil)",
        "research_area": "digital procurement",
        "study_context": "Public institutions in Ghana are adopting digital procurement systems with different levels of transparency.",
        "research_approach": "Quantitative",
        "data_type": "Primary survey data",
        "objectives": [
            "Examine the effect of digital procurement maturity on transparency",
            "Assess the effect of transparency on procurement accountability",
        ],
        "research_questions": [
            "What is the effect of digital procurement maturity on transparency?",
            "What is the effect of transparency on procurement accountability?",
        ],
        "hypotheses": [
            "H1: Digital procurement maturity has a significant positive effect on transparency",
            "H2: Transparency has a significant positive effect on procurement accountability",
        ],
        "variables": {"raw_variables": ["Digital procurement maturity", "Transparency", "Procurement accountability"]},
        "expected_chapters": 5,
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }


def test_research_logic_cockpit_and_profile_update(tmp_path, monkeypatch):
    _, database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json=_project_payload())
    assert created.status_code == 200
    project_id = created.json()["id"]

    updated = client.put(
        f"/api/projects/{project_id}/profile",
        json={
            "title": _project_payload()["title"],
            "objectives": _project_payload()["objectives"],
            "research_questions": _project_payload()["research_questions"],
            "hypotheses": _project_payload()["hypotheses"],
            "variables": _project_payload()["variables"],
            "research_approach": "Quantitative",
            "data_type": "Primary survey data",
            "study_context": _project_payload()["study_context"],
        },
    )
    assert updated.status_code == 200
    logic = updated.json()["research_logic"]
    assert logic["objectives_count"] == 2
    assert logic["questions_count"] == 2
    assert logic["variables_count"] == 3
    assert len(logic["objective_matrix"]) == 2
    assert logic["readiness_label"] == "Project workflow readiness, not a grade"

    fetched = client.get(f"/api/projects/{project_id}/research-logic")
    assert fetched.status_code == 200
    assert fetched.json()["alignment_score"] >= 50


def test_version_history_can_restore_chapter_snapshot(tmp_path, monkeypatch):
    _, database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json=_project_payload()).json()
    project_id = created["id"]

    first = database.save_draft_version(project_id, 1, "First chapter version with enough text for recovery.", source="test", label="First")
    second = database.save_draft_version(project_id, 1, "Second chapter version with revised content.", source="test", label="Second")
    assert second["version_number"] == first["version_number"] + 1

    versions = client.get(f"/api/projects/{project_id}/versions/1")
    assert versions.status_code == 200
    assert len(versions.json()["versions"]) == 2

    restored = client.post(f"/api/projects/{project_id}/versions/1/{first['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["draft"].startswith("First chapter version")

    with database.get_conn() as conn:
        row = conn.execute("SELECT drafts_json FROM projects WHERE id = ?", (project_id,)).fetchone()
    drafts = json.loads(dict(row)["drafts_json"])
    assert drafts["1"].startswith("First chapter version")


def test_project_working_file_compiler_combines_saved_chapters(tmp_path, monkeypatch):
    _, database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    created = client.post("/api/projects", json=_project_payload()).json()
    project_id = created["id"]

    with database.get_conn() as conn:
        conn.execute(
            "UPDATE projects SET drafts_json = ? WHERE id = ?",
            (json.dumps({"1": "# Background\n\nChapter one content.", "2": "# Literature Review\n\nChapter two content."}), project_id),
        )
        conn.commit()

    response = client.get(f"/api/projects/{project_id}/export/project-working-file")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    out = tmp_path / "compiled.docx"
    out.write_bytes(response.content)
    doc = Document(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Chapter 1: Introduction" in text
    assert "Chapter 2: Literature Review" in text
    assert "ProjectReady Working-File Audit Note" in text


def test_workspace_keeps_chapter_drafting_and_adds_cockpit(tmp_path, monkeypatch):
    _, _, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    page = client.get("/workspace")
    assert page.status_code == 200
    assert "Student Research Cockpit" in page.text
    assert "Develop Chapter Draft" in page.text
    assert "Research alignment matrix" in page.text
    assert "Compile Project Working File DOCX" in page.text
