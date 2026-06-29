from fastapi import HTTPException

from app.routers.generation import _validate_guided_development_request
from app.schemas import DraftRequest


def _payload(**overrides):
    values = {
        "chapter_number": 1,
        "selected_section_ids": ["ch1_background", "ch1_problem"],
        "answers": {
            "ch1_background": {
                "q1": "The study examines exchange-rate pass-through to consumer inflation in Ghana using monthly macroeconomic data and a clearly defined policy context."
            }
        },
        "academic_integrity_confirmed": True,
        "user_contribution_confirmed": True,
    }
    values.update(overrides)
    return DraftRequest(**values)


def _project():
    return {
        "title": "Exchange-rate pass-through and consumer inflation in Ghana",
        "profile": {
            "title": "Exchange-rate pass-through and consumer inflation in Ghana",
            "research_area": "Exchange-rate pass-through",
            "study_context": "The study focuses on Ghana and the transmission of exchange-rate movements to domestic consumer prices.",
            "objectives": [
                "To estimate the degree of exchange-rate pass-through to consumer inflation in Ghana."
            ],
            "citation_evidence_notes": "Verified Bank of Ghana inflation and exchange-rate series, together with peer-reviewed Ghanaian pass-through studies.",
            "student_contribution": {
                "central_argument": "The chapter should explain why incomplete and asymmetric pass-through matters for monetary policy.",
                "local_context_notes": "The analysis is situated within Ghana's inflation-targeting and exchange-rate volatility experience.",
            },
            "source_bank": [{"title": "Exchange Rate Pass-Through in Ghana", "year": 2010}],
        },
    }


def test_declaration_is_required_before_working_draft_development():
    payload = _payload(academic_integrity_confirmed=False)
    try:
        _validate_guided_development_request(
            _project(), payload, revision_mode=False, revision_text=""
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "academic-integrity" in exc.detail["message"]
    else:
        raise AssertionError("Expected academic-integrity declaration to be required")


def test_meaningful_user_inputs_pass_the_readiness_gate():
    _validate_guided_development_request(
        _project(), _payload(), revision_mode=False, revision_text=""
    )


def test_chapter_four_requires_user_supplied_results():
    payload = _payload(chapter_number=4, selected_section_ids=["ch4_results"])
    try:
        _validate_guided_development_request(
            _project(), payload, revision_mode=False, revision_text=""
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert any("actual results" in item for item in exc.detail["missing"])
    else:
        raise AssertionError("Expected Chapter Four to require uploaded results")


def test_project_creation_schema_defaults_to_unconfirmed_responsible_use():
    from app.schemas import ProjectCreate

    project = ProjectCreate(title="A valid research title")
    assert project.academic_integrity_confirmed is False
    assert project.user_contribution_confirmed is False
