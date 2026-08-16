from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.research_journey import approach_family, build_journey, final_audit

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def base_project(**profile_updates):
    profile = {
        "title": "Teacher leadership and instructional practice",
        "level": "Research Masters (e.g. MPhil)",
        "research_area": "Educational leadership",
        "study_context": "Basic schools in the Ashanti Region of Ghana",
        "research_approach": "Quantitative",
        "data_type": "Primary survey data",
        "expected_chapters": 5,
        "objectives": ["Examine the relationship between teacher trust and teacher leadership"],
        "research_questions": ["What relationship exists between teacher trust and teacher leadership?"],
        "hypotheses": ["Teacher trust is positively related to teacher leadership"],
        "variables": {"raw_variables": ["teacher trust", "teacher leadership"]},
        "source_bank": [{"title": f"Source {i}"} for i in range(10)],
        "selected_papers": [],
    }
    profile.update(profile_updates)
    return {"id": "p1", "title": profile["title"], "profile": profile, "drafts": {}, "checks": {}}


def test_research_journey_has_twelve_adaptive_stages_and_what_next():
    journey = build_journey(base_project())
    assert len(journey["stages"]) == 12
    assert journey["stages"][0]["label"] == "Research Setup"
    assert journey["stages"][-1]["label"] == "Viva Preparation"
    assert journey["what_next"]["label"] in {stage["label"] for stage in journey["stages"]}
    assert journey["approach_family"] == "quantitative"


def test_qualitative_and_mixed_methods_paths_require_their_specific_decisions():
    qualitative = base_project(research_approach="Qualitative", data_type="Qualitative data", hypotheses=[], variables={})
    mixed = base_project(research_approach="Mixed methods", data_type="Mixed methods")
    assert approach_family(qualitative["profile"]) == "qualitative"
    assert approach_family(mixed["profile"]) == "mixed_methods"
    q_journey = build_journey(qualitative)
    m_journey = build_journey(mixed)
    design_q = next(stage for stage in q_journey["stages"] if stage["key"] == "design")
    design_m = next(stage for stage in m_journey["stages"] if stage["key"] == "design")
    assert any("coding" in item.lower() for item in design_q["missing"])
    assert any("integration" in item.lower() for item in design_m["missing"])


def test_final_audit_checks_claim_support_and_supervisor_corrections():
    project = base_project(
        claim_support_reviews={"draft:1": {"final_output_ready": False}},
        supervisor_corrections=[{"id": "c1", "comment": "Revise problem", "status": "open"}],
    )
    audit = final_audit(project, {"issues": [], "compliance_score": 90})
    by_key = {item["key"]: item for item in audit["checks"]}
    assert by_key["claim_support"]["status"] == "needs_action"
    assert by_key["supervisor_corrections"]["status"] == "needs_action"


def test_five_main_modules_and_complete_guide_ui_are_present():
    homepage = (STATIC / "index.html").read_text(encoding="utf-8")
    workspace = (STATIC / "workspace.html").read_text(encoding="utf-8")
    strengthener = (STATIC / "chapter_strengthener.html").read_text(encoding="utf-8")
    for label in ["Research Journey", "Quick Chapter Development", "Review &amp; Strengthen", "Research Coach", "My Research Projects"]:
        assert label in homepage
    for marker in ["My Research Record", "Research Decision checkpoints", "Supervisor Corrections", "Final Research Audit", "journeyStageGrid"]:
        assert marker in workspace
    for mode in ["Resolve Citation Gaps", "Apply Supervisor Corrections", "Check Research Alignment", "Check Results &amp; Interpretation", "Review Methodology"]:
        assert mode in strengthener


def test_new_public_module_routes_are_served():
    with TestClient(app) as client:
        for route in ["/research-journey", "/quick-chapter", "/review-strengthen", "/research-coach", "/my-projects"]:
            response = client.get(route)
            assert response.status_code == 200, route
