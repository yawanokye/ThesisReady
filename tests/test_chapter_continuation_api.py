from __future__ import annotations

import importlib
import json

from fastapi.testclient import TestClient

from app.template_store import selected_sections


def _reload_app(tmp_path, monkeypatch):
    db = tmp_path / "continuation-projectready.db"
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
    return database, main


def _payload():
    return {
        "title": "Digital Procurement and Transparency",
        "programme": "MPhil Procurement",
        "level": "Research Masters (e.g. MPhil)",
        "research_area": "procurement transparency",
        "study_context": "Public institutions in Ghana",
        "research_approach": "Quantitative",
        "objectives": ["Examine the effect of digital procurement on transparency"],
        "research_questions": ["How does digital procurement affect transparency?"],
        "hypotheses": ["H1: Digital procurement positively affects transparency"],
        "variables": {"raw_variables": ["Digital procurement", "Transparency"]},
        "expected_chapters": 5,
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }


def test_continuation_api_requires_complete_chapter_and_carries_logic(tmp_path, monkeypatch):
    database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    project_id = client.post("/api/projects", json=_payload()).json()["id"]

    incomplete = [section["section_id"] for section in selected_sections(1, [])][:3]
    with database.get_conn() as conn:
        conn.execute(
            "UPDATE projects SET drafts_json = ?, selected_sections_json = ? WHERE id = ?",
            (json.dumps({"1": "# Chapter One\n\nA partial draft."}), json.dumps({"1": incomplete}), project_id),
        )
        conn.commit()
    response = client.get(f"/api/projects/{project_id}/continuation/1")
    assert response.status_code == 200
    assert response.json()["linkage"]["available"] is False

    complete = [section["section_id"] for section in selected_sections(1, [])]
    with database.get_conn() as conn:
        conn.execute(
            "UPDATE projects SET selected_sections_json = ? WHERE id = ?",
            (json.dumps({"1": complete}), project_id),
        )
        conn.commit()
    response = client.get(f"/api/projects/{project_id}/continuation/1")
    assert response.status_code == 200
    linkage = response.json()["linkage"]
    assert linkage["available"] is True
    assert linkage["next_chapter"] == 2
    assert linkage["title"] == _payload()["title"]
    assert linkage["objectives"] == _payload()["objectives"]


def test_provisional_statistic_confirmation_endpoint_is_source_bound(tmp_path, monkeypatch):
    database, main = _reload_app(tmp_path, monkeypatch)
    client = TestClient(main.app)
    payload = _payload()
    payload["source_bank"] = [{
        "authors": ["Ama Mensah"],
        "year": 2025,
        "title": "Digital procurement survey",
        "doi": "10.1000/digital-procurement",
        "abstract": "The survey found that 61% of 350 respondents reported using the digital procurement platform regularly.",
    }]
    project_id = client.post("/api/projects", json=payload).json()["id"]

    # The continuation endpoint refreshes only source-grounded candidates.
    complete = [section["section_id"] for section in selected_sections(1, [])]
    draft = "# Chapter One\n\n[CONFIRM SOURCED STATISTIC: The survey found that 61% of 350 respondents reported using the digital procurement platform regularly. | Source: Mensah (2025). Digital procurement survey | https://doi.org/10.1000/digital-procurement]"
    with database.get_conn() as conn:
        conn.execute(
            "UPDATE projects SET drafts_json = ?, selected_sections_json = ? WHERE id = ?",
            (json.dumps({"1": draft}), json.dumps({"1": complete}), project_id),
        )
        conn.commit()
    linkage = client.get(f"/api/projects/{project_id}/continuation/1").json()["linkage"]
    assert len(linkage["provisional_statistics"]) == 1
    candidate = linkage["provisional_statistics"][0]
    assert candidate["status"] == "pending"

    confirmed = client.post(
        f"/api/projects/{project_id}/provisional-statistics/{candidate['id']}/decision",
        json={"decision": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["statistic"]["status"] == "confirmed"
