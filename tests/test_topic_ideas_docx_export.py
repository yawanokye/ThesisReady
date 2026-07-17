from __future__ import annotations

import importlib
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "topic-export.db"))
    import app.database as database
    import app.payments.store as store
    import app.routers.topic_ideas as topic_router
    import app.main as main

    importlib.reload(database)
    importlib.reload(store)
    importlib.reload(topic_router)
    importlib.reload(main)
    return TestClient(main.app)


def _result():
    return {
        "research_area": "employee competence and administrative performance",
        "selected_level": "Research Masters / MPhil",
        "free_preview": False,
        "ideas_returned": 1,
        "trend_summary": "Recent work links competence and administrative performance, but the Ghanaian university context remains underexamined.",
        "query": "employee competence administrative performance Ghana university",
        "recent_reference_window": "2021-2026",
        "ideas": [
            {
                "title": "Employee Competence and Administrative Performance in a Ghanaian Public University",
                "synopsis": "A focused quantitative survey of administrative staff.",
                "proposed_objectives": {
                    "general_objective": "To examine the relationship between employee competence and administrative performance.",
                    "specific_objectives": [
                        "To assess employee competence.",
                        "To assess administrative performance.",
                    ],
                    "level_alignment": "Suitable for MPhil-level construct testing.",
                },
                "current_research_trend_or_gap": "The exact public-university administrative context remains underexamined.",
                "possible_methodology": "Cross-sectional quantitative survey.",
                "possible_variables_or_constructs": ["employee competence", "administrative performance"],
                "possible_data_sources": ["Primary questionnaire responses from administrative staff."],
                "research_resource_guidance": {
                    "secondary_data_sources": [],
                    "questionnaire_or_instrument_sources": [
                        {
                            "title": "Training and development among senior administrative staff",
                            "authors": ["A. Author"],
                            "year": 2024,
                            "source": "Journal of University Administration",
                            "url": "https://example.org/article",
                            "candidate_use": "Possible source of questionnaire items.",
                            "matched_constructs": ["administrative performance"],
                        }
                    ],
                },
                "potential_contribution": "Provides context-specific evidence for university staff development.",
            }
        ],
        "source_records_used": [
            {
                "title": "Employee competence and performance",
                "authors": ["B. Researcher"],
                "year": 2023,
                "source": "Human Resource Journal",
                "url": "https://example.org/source",
            }
        ],
    }


def test_topic_ideas_can_be_exported_to_docx(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/topic-ideas/export-docx", json={"result": _result()})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    document = Document(BytesIO(response.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "ProjectReady AI Topic Ideas" in text
    assert "Employee Competence and Administrative Performance" in text
    assert "Strongly matched instrument candidates" in text
    assert "Employee Ownership Trusts" not in text


def test_topic_ideas_export_requires_generated_ideas(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/topic-ideas/export-docx", json={"result": {"ideas": []}})
    assert response.status_code == 400
