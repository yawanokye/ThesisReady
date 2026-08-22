from __future__ import annotations

import re
from typing import Any


def clean_list(value: Any, limit: int = 30) -> list[str]:
    if isinstance(value, str):
        raw = value.splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = re.sub(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\s*[.)-]\s*", "", str(item or "").strip(), flags=re.I)
        key = text.casefold()
        if len(text) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(text[:1200])
        if len(out) >= limit:
            break
    return out


def approach_family(profile: dict[str, Any]) -> str:
    text = " ".join([
        str(profile.get("research_approach") or ""),
        str(profile.get("data_type") or ""),
        str(profile.get("thesis_format") or ""),
    ]).lower()
    if "mixed" in text:
        return "mixed_methods"
    if any(token in text for token in ("qualitative", "case-study", "case study", "phenomen", "ethnograph", "grounded theory")):
        return "qualitative"
    return "quantitative"


def _variables(profile: dict[str, Any]) -> list[str]:
    raw = profile.get("variables") or []
    if isinstance(raw, dict):
        raw = raw.get("raw_variables") or raw.get("constructs") or raw.get("variables") or []
    return clean_list(raw, 40)


def research_record(profile: dict[str, Any], project_title: str = "") -> dict[str, Any]:
    return {
        "identity": {
            "title": str(project_title or profile.get("title") or "").strip(),
            "level": str(profile.get("level") or "").strip(),
            "programme": str(profile.get("programme") or "").strip(),
            "department": str(profile.get("department") or "").strip(),
            "institution": str(profile.get("institution") or "").strip(),
            "research_area": str(profile.get("research_area") or "").strip(),
            "study_context": str(profile.get("study_context") or "").strip(),
        },
        "logic": {
            "objectives": clean_list(profile.get("objectives"), 20),
            "research_questions": clean_list(profile.get("research_questions"), 20),
            "hypotheses": clean_list(profile.get("hypotheses"), 30),
            "variables": _variables(profile),
        },
        "theory_framework": {
            "theoretical_framework": str(profile.get("theoretical_framework") or "").strip(),
            "conceptual_framework_summary": str(profile.get("conceptual_framework_summary") or "").strip(),
            "conceptual_framework_paths": profile.get("conceptual_framework_paths") if isinstance(profile.get("conceptual_framework_paths"), list) else [],
            "conceptual_framework_optional": True,
        },
        "method": {
            "research_approach": str(profile.get("research_approach") or "").strip(),
            "research_design": str(profile.get("research_design") or "").strip(),
            "philosophy": str(profile.get("philosophy") or "").strip(),
            "population": str(profile.get("population") or "").strip(),
            "sample_size": str(profile.get("sample_size") or "").strip(),
            "sampling_strategy": str(profile.get("sampling_strategy") or "").strip(),
            "participants": str(profile.get("participants") or "").strip(),
            "instruments": str(profile.get("instruments") or "").strip(),
            "validity_reliability": str(profile.get("validity_reliability") or "").strip(),
            "trustworthiness": str(profile.get("trustworthiness") or "").strip(),
            "ethics": str(profile.get("ethics") or "").strip(),
            "analysis_plan": str(profile.get("analysis_plan") or "").strip(),
            "coding_approach": str(profile.get("coding_approach") or "").strip(),
            "mixed_methods_design": str(profile.get("mixed_methods_design") or "").strip(),
            "integration_strategy": str(profile.get("integration_strategy") or "").strip(),
        },
        "evidence": {
            "citation_discipline_matrix": str(profile.get("citation_discipline_matrix") or "auto"),
            "source_count": len([x for x in (profile.get("source_bank") or []) if isinstance(x, dict)]),
            "selected_paper_count": len([x for x in (profile.get("selected_papers") or []) if isinstance(x, dict)]),
        },
        "decisions": profile.get("research_decisions") if isinstance(profile.get("research_decisions"), dict) else {},
    }


def decision_checkpoints(profile: dict[str, Any]) -> list[dict[str, Any]]:
    family = approach_family(profile)
    saved = profile.get("research_decisions") if isinstance(profile.get("research_decisions"), dict) else {}
    specs = [
        ("research_design", "Research design", "Confirm the design that best fits the approved purpose, questions and data structure."),
        ("theoretical_framework", "Theory/theoretical framework", "Confirm the theoretical basis rather than allowing the system to silently choose it."),
        ("sampling_strategy", "Sampling strategy", "Confirm how participants, cases or records will be selected and why the approach is defensible."),
        ("analysis_plan", "Analysis plan", "Confirm how each objective/question/hypothesis will be analysed before results are interpreted."),
        ("conceptual_framework", "Conceptual framework (optional)", "Use a conceptual framework when it helps clarify constructs, mediators, moderators or paths. Analysis may proceed without it when the objectives, design and data structure are sufficient."),
    ]
    if family == "qualitative":
        specs.insert(1, ("philosophical_position", "Philosophical position", "Confirm the philosophical or interpretive position where the design requires it."))
    if family == "mixed_methods":
        specs.append(("mixed_methods_integration", "Mixed-methods integration", "Confirm where and how the quantitative and qualitative strands will be integrated."))
    items: list[dict[str, Any]] = []
    for key, label, prompt in specs:
        value = saved.get(key) if isinstance(saved, dict) else None
        if isinstance(value, dict):
            status = str(value.get("status") or "pending")
            selection = str(value.get("selection") or "")
            rationale = str(value.get("rationale") or "")
        else:
            status, selection, rationale = "pending", "", ""
        items.append({"key": key, "label": label, "prompt": prompt, "status": status, "selection": selection, "rationale": rationale})
    return items


def _draft_state(project: dict[str, Any]) -> tuple[int, int, int]:
    drafts = project.get("drafts") or {}
    expected = max(1, min(int((project.get("profile") or {}).get("expected_chapters") or 5), 9))
    developed = 0
    started = 0
    for number in range(1, expected + 1):
        text = str(drafts.get(str(number)) or "")
        words = len(re.findall(r"\b\w+\b", text))
        if words >= 900:
            developed += 1
        elif words >= 120:
            started += 1
    return expected, developed, started


def build_journey(project: dict[str, Any]) -> dict[str, Any]:
    profile = project.get("profile") or {}
    family = approach_family(profile)
    record = research_record(profile, str(project.get("title") or ""))
    identity = record["identity"]
    logic = record["logic"]
    method = record["method"]
    evidence = record["evidence"]
    expected, developed, started = _draft_state(project)
    decisions = decision_checkpoints(profile)
    unresolved_decisions = [item for item in decisions if item["status"] not in {"approved", "confirmed"} and item.get("key") != "conceptual_framework"]
    corrections = profile.get("supervisor_corrections") if isinstance(profile.get("supervisor_corrections"), list) else []
    open_corrections = [item for item in corrections if isinstance(item, dict) and str(item.get("status") or "open") not in {"resolved", "ignored"}]

    setup_missing = []
    if not identity["title"]: setup_missing.append("research title")
    if not identity["research_area"]: setup_missing.append("research area")
    if len(identity["study_context"]) < 20: setup_missing.append("study context")
    logic_missing = []
    if not logic["objectives"]: logic_missing.append("specific objectives")
    if len(logic["research_questions"]) < len(logic["objectives"]): logic_missing.append("research questions mapped to objectives")
    if family in {"quantitative", "mixed_methods"} and not logic["variables"]: logic_missing.append("key constructs/variables")
    if family in {"quantitative", "mixed_methods"} and logic["objectives"] and not logic["hypotheses"]: logic_missing.append("hypotheses where substantively required")
    evidence_missing = []
    total_sources = int(evidence["source_count"]) + int(evidence["selected_paper_count"])
    if total_sources < 8: evidence_missing.append("a stronger verified evidence base")
    theory_missing = []
    if not record["theory_framework"]["theoretical_framework"]: theory_missing.append("approved theory/theoretical framework")
    # A conceptual framework is optional. When supplied it can guide variable roles, mediation/moderation and SEM paths, but its absence must not block analysis.
    design_missing = []
    if not method["research_approach"]: design_missing.append("research approach")
    if not method["research_design"]: design_missing.append("research design")
    if family == "qualitative":
        if not method["participants"] and not method["population"]: design_missing.append("participants/cases")
        if not method["sampling_strategy"]: design_missing.append("participant/case selection strategy")
        if not method["coding_approach"]: design_missing.append("coding/analytic approach")
        if not method["trustworthiness"]: design_missing.append("trustworthiness strategy")
    else:
        if not method["population"]: design_missing.append("population")
        if not method["sample_size"]: design_missing.append("sample size or approved sample basis")
        if not method["sampling_strategy"]: design_missing.append("sampling strategy")
        if not method["instruments"]: design_missing.append("instrument/measurement plan")
    if family == "mixed_methods":
        if not method["mixed_methods_design"]: design_missing.append("mixed-methods design")
        if not method["integration_strategy"]: design_missing.append("integration strategy")
    if not method["ethics"]: design_missing.append("ethics plan/approval information")
    if not method["analysis_plan"]: design_missing.append("analysis plan")

    stages = [
        {"key":"setup","number":1,"label":"Research Setup","description":"Topic, level, discipline and study context.","href":"/workspace#projectSetupStep","missing":setup_missing},
        {"key":"logic","number":2,"label":"Problem & Research Logic","description":"Problem, objectives, questions, hypotheses and variables.","href":"/workspace#researchCockpit","missing":logic_missing},
        {"key":"evidence","number":3,"label":"Evidence & Literature","description":"Find, upload, verify and organise scholarly evidence.","href":"/workspace#sourceSearchQuery","missing":evidence_missing},
        {"key":"theory","number":4,"label":"Theory & Conceptual Framework","description":"Confirm theory, constructs and the conceptual framework.","href":"/workspace#researchRecordPanel","missing":theory_missing},
        {"key":"design","number":5,"label":"Research Design","description":"Design, sampling, instruments, ethics and analysis plan.","href":"/workspace#researchRecordPanel","missing":design_missing},
        {"key":"chapters","number":6,"label":"Develop Chapters","description":"Develop full chapters or selected sections using the saved research record.","href":"/quick-chapter","missing":[] if developed or started else ["first chapter working draft"]},
        {"key":"strengthen","number":7,"label":"Review & Strengthen","description":"Strengthen existing work, resolve citation gaps and apply supervisor guidance.","href":"/review-strengthen","missing":[]},
        {"key":"analysis","number":8,"label":"Data & Analysis Workspace","description":("Traceable qualitative coding, themes and mixed-methods integration." if family == "qualitative" else "Upload raw data, compute descriptives/diagnostics and estimate regression, time-series, panel, mediation, moderation or SEM models."),"href":"/data-analysis","missing":[] if (profile.get("analysis_run_summaries") or method["analysis_plan"]) else ["analysis plan or first verified analysis run"]},
        {"key":"supervisor","number":9,"label":"Supervisor Corrections","description":"Track, address, ignore with reason and resolve supervisor comments.","href":"/review-strengthen#strengthenerOptionalSupport","missing":[f"{len(open_corrections)} open correction(s)"] if open_corrections else []},
        {"key":"audit","number":10,"label":"Final Research Audit","description":"Check objective coverage, citations, references, results and conclusions.","href":"/workspace#reviewStep","missing":[] if developed >= expected and not unresolved_decisions else ([f"{expected-developed} chapter(s) not yet complete"] if developed < expected else []) + ([f"{len(unresolved_decisions)} research decision(s) pending"] if unresolved_decisions else [])},
        {"key":"compile","number":11,"label":"Compile Thesis","description":"Compile the project working file after research and evidence checks.","href":"/workspace#compileProjectBtn","missing":[] if developed >= expected else [f"complete {expected-developed} remaining chapter(s)"]},
        {"key":"viva","number":12,"label":"Viva Preparation","description":"Prepare to defend theory, method, findings, contribution and limitations.","href":"/research-coach?mode=viva","missing":[] if developed >= expected else ["complete the substantive thesis before final viva preparation"]},
    ]
    for stage in stages:
        if stage["key"] in {"strengthen", "supervisor"} and not stage["missing"]:
            stage["status"] = "available"
        elif not stage["missing"]:
            stage["status"] = "complete" if stage["key"] not in {"chapters", "analysis", "audit", "compile", "viva"} else "ready"
        else:
            stage["status"] = "needs_input"
    # Chapter stage gets real progress semantics.
    chapters = next(item for item in stages if item["key"] == "chapters")
    if developed >= expected:
        chapters["status"] = "complete"
    elif developed or started:
        chapters["status"] = "in_progress"
        chapters["missing"] = [f"{developed} of {expected} chapter(s) substantially developed"]

    priority = next((stage for stage in stages if stage["status"] == "needs_input" and stage["key"] not in {"viva"}), None)
    if not priority:
        priority = next((stage for stage in stages if stage["status"] in {"in_progress", "ready"} and stage["key"] in {"chapters", "analysis", "audit", "compile"}), stages[-1])
    what_next = {
        "label": priority["label"],
        "message": ("Provide: " + ", ".join(priority["missing"]) + ".") if priority.get("missing") else priority["description"],
        "href": priority["href"],
        "stage_key": priority["key"],
        "missing": priority.get("missing") or [],
    }
    return {
        "approach_family": family,
        "approach_label": {"quantitative":"Quantitative journey","qualitative":"Qualitative journey","mixed_methods":"Mixed-methods journey"}[family],
        "stages": stages,
        "what_next": what_next,
        "decision_checkpoints": decisions,
        "research_record": record,
        "progress": {"expected_chapters": expected, "developed_chapters": developed, "started_chapters": started, "open_supervisor_corrections": len(open_corrections)},
        "supervisor_corrections": [item for item in corrections if isinstance(item, dict)][-100:],
    }


def final_audit(project: dict[str, Any], logic: dict[str, Any] | None = None) -> dict[str, Any]:
    journey = build_journey(project)
    logic = logic or {}
    checks: list[dict[str, Any]] = []
    record = journey["research_record"]
    profile = project.get("profile") or {}
    obj = record["logic"]["objectives"]
    rq = record["logic"]["research_questions"]
    checks.append({"key":"objective_question_alignment","label":"Objectives and questions","status":"pass" if obj and len(rq) >= len(obj) else "needs_action","message":"Every objective should trace to a research question."})
    required_decisions = [d for d in journey["decision_checkpoints"] if d.get("key") != "conceptual_framework"]
    checks.append({"key":"decision_checkpoints","label":"Research decisions","status":"pass" if all(d["status"] in {"approved","confirmed"} for d in required_decisions) else "needs_action","message":"Confirm major theory, design, sampling and analysis decisions. The conceptual framework is optional."})
    developed = journey["progress"]["developed_chapters"]
    expected = journey["progress"]["expected_chapters"]
    checks.append({"key":"chapter_completion","label":"Chapter coverage","status":"pass" if developed >= expected else "needs_action","message":f"{developed} of {expected} expected chapters are substantially developed."})
    source_count = int(record["evidence"]["source_count"]) + int(record["evidence"]["selected_paper_count"])
    checks.append({"key":"evidence_base","label":"Evidence base","status":"pass" if source_count >= 8 else "needs_action","message":f"{source_count} attached/discovered source records are currently available. Claim-level verification remains required."})
    analysis_runs = profile.get("analysis_run_summaries") if isinstance(profile.get("analysis_run_summaries"), list) else []
    checks.append({"key":"data_analysis","label":"Verified data analysis","status":"pass" if analysis_runs or journey.get("approach_family") == "qualitative" else "needs_action","message":(f"{len(analysis_runs)} deterministic analysis run(s) are recorded." if analysis_runs else "Run or attach the approved analysis in the Data & Analysis Workspace before final quantitative results are treated as verified.")})
    profile = project.get("profile") or {}
    reviews = profile.get("claim_support_reviews") if isinstance(profile.get("claim_support_reviews"), dict) else {}
    unresolved_reviews = [key for key, value in reviews.items() if isinstance(value, dict) and not bool(value.get("final_output_ready"))]
    checks.append({
        "key":"claim_support",
        "label":"Claim support and citation density",
        "status":"pass" if reviews and not unresolved_reviews else "needs_action",
        "message": ("All stored claim-support reviews currently pass." if reviews and not unresolved_reviews else (f"{len(unresolved_reviews)} stored chapter review(s) still contain unsupported claims or paragraph-density gaps." if unresolved_reviews else "Run Claim Support Review on developed chapters before final compilation.")),
    })
    corrections = profile.get("supervisor_corrections") if isinstance(profile.get("supervisor_corrections"), list) else []
    open_corrections = [item for item in corrections if isinstance(item, dict) and str(item.get("status") or "open") not in {"resolved", "ignored"}]
    checks.append({"key":"supervisor_corrections","label":"Supervisor corrections","status":"pass" if not open_corrections else "needs_action","message":"No open tracked supervisor correction remains." if not open_corrections else f"{len(open_corrections)} supervisor correction(s) remain open or are being addressed."})
    issues = logic.get("issues") if isinstance(logic, dict) else []
    checks.append({"key":"logic_issues","label":"Cross-chapter research logic","status":"pass" if not issues else "needs_action","message":"No deterministic cross-chapter issue detected." if not issues else str((issues or [{}])[0].get("message") or "Resolve research-logic issues.")})
    compliance = logic.get("compliance_score") if isinstance(logic, dict) else None
    checks.append({"key":"compliance","label":"Academic compliance checks","status":"pass" if isinstance(compliance, (int, float)) and compliance >= 80 else "needs_action","message":f"Current average compliance score: {round(float(compliance),1)}%." if isinstance(compliance,(int,float)) else "Run chapter compliance checks before final compilation."})
    passed = sum(1 for c in checks if c["status"] == "pass")
    return {"checks": checks, "passed": passed, "total": len(checks), "ready": passed == len(checks), "note":"This is a workflow audit, not academic approval. Supervisor/institutional review remains required."}
