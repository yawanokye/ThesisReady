from __future__ import annotations

import re
from typing import Any

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "among", "within", "between", "through",
    "this", "that", "these", "those", "study", "research", "effect", "effects", "impact", "role",
    "relationship", "relationships", "influence", "assess", "examine", "determine", "investigate",
    "evaluate", "analyse", "analyze", "explore", "understand", "using", "use", "based", "level",
    "extent", "whether", "how", "what", "which", "their", "there", "have", "has", "were", "was",
}

CHAPTER_NAMES = {
    1: "Introduction",
    2: "Literature Review",
    3: "Research Methods/Methodology",
    4: "Results/Data Analysis and Discussion",
    5: "Summary, Conclusion and Recommendation",
    6: "Other Chapter",
    7: "Supplementary Methods Chapter",
}


def _clean_list(value: Any, limit: int = 30) -> list[str]:
    if isinstance(value, str):
        items = [line.strip() for line in value.splitlines()]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item or "").strip() for item in value]
    else:
        items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = re.sub(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\s*[.)-]\s*", "", item, flags=re.I).strip()
        key = item.casefold()
        if len(item) < 3 or key in seen:
            continue
        seen.add(key)
        result.append(item[:800])
        if len(result) >= limit:
            break
    return result


def _variables(profile: dict[str, Any]) -> list[str]:
    raw = profile.get("variables") or []
    if isinstance(raw, dict):
        raw = raw.get("raw_variables") or raw.get("constructs") or raw.get("variables") or []
    return _clean_list(raw, 40)


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", str(value or "").lower())
    return {word for word in words if word not in STOPWORDS}


def _mentions(text: str, statement: str) -> bool:
    haystack = str(text or "").lower()
    statement_text = str(statement or "").strip().lower()
    if not haystack or not statement_text:
        return False
    if len(statement_text) >= 18 and statement_text in haystack:
        return True
    wanted = list(_tokens(statement_text))
    if not wanted:
        return False
    hits = sum(1 for token in wanted if re.search(rf"\b{re.escape(token)}\b", haystack))
    required = 1 if len(wanted) <= 2 else 2 if len(wanted) <= 5 else 3
    return hits >= required and hits / max(len(wanted), 1) >= 0.35


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", str(text or "")))


def _chapter_statuses(project: dict[str, Any], expected_chapters: int) -> list[dict[str, Any]]:
    drafts = project.get("drafts") or {}
    checks = project.get("checks") or {}
    statuses: list[dict[str, Any]] = []
    max_chapter = max(1, min(int(expected_chapters or 5), 9))
    for number in range(1, max_chapter + 1):
        draft = str(drafts.get(str(number)) or "")
        words = _word_count(draft)
        check = checks.get(str(number)) or {}
        score = check.get("score_percent") if isinstance(check, dict) else None
        if words >= 900:
            state = "developed"
        elif words >= 120:
            state = "started"
        else:
            state = "not_started"
        statuses.append({
            "chapter_number": number,
            "chapter_title": CHAPTER_NAMES.get(number, f"Chapter {number}"),
            "status": state,
            "word_count": words,
            "compliance_score": score,
        })
    return statuses


def build_research_logic(project: dict[str, Any]) -> dict[str, Any]:
    profile = project.get("profile") or {}
    drafts = project.get("drafts") or {}
    checks = project.get("checks") or {}

    title = str(project.get("title") or profile.get("title") or "").strip()
    level = str(profile.get("level") or "Bachelors").strip()
    approach = str(profile.get("research_approach") or "").strip()
    data_type = str(profile.get("data_type") or "").strip()
    context = str(profile.get("study_context") or "").strip()
    objectives = _clean_list(profile.get("objectives"), 20)
    questions = _clean_list(profile.get("research_questions"), 20)
    hypotheses = _clean_list(profile.get("hypotheses"), 20)
    variables = _variables(profile)
    expected_chapters = int(profile.get("expected_chapters") or 5)
    chapter_status = _chapter_statuses(project, expected_chapters)

    source_bank = profile.get("source_bank") or []
    if not isinstance(source_bank, list):
        source_bank = []
    source_count = len([item for item in source_bank if isinstance(item, dict)])

    lower_approach = approach.lower()
    hypotheses_expected = any(term in lower_approach for term in ("quant", "mixed")) and len(objectives) > 0

    chapter4 = str(drafts.get("4") or "")
    chapter5 = str(drafts.get("5") or "")
    matrix: list[dict[str, Any]] = []
    for index, objective in enumerate(objectives):
        question = questions[index] if index < len(questions) else ""
        hypothesis = hypotheses[index] if index < len(hypotheses) else ""
        result_covered = _mentions(chapter4, objective)
        conclusion_covered = _mentions(chapter5, objective)
        gaps: list[str] = []
        if not question:
            gaps.append("Research question not mapped")
        if hypotheses_expected and not hypothesis:
            gaps.append("Hypothesis not mapped")
        if chapter4.strip() and not result_covered:
            gaps.append("Not clearly traceable in Chapter Four")
        if chapter5.strip() and not conclusion_covered:
            gaps.append("Not clearly traceable in Chapter Five")
        if not gaps:
            status = "aligned"
        elif len(gaps) <= 1:
            status = "partial"
        else:
            status = "needs_action"
        matrix.append({
            "objective_number": index + 1,
            "objective": objective,
            "research_question": question,
            "hypothesis": hypothesis,
            "result_covered": result_covered,
            "conclusion_covered": conclusion_covered,
            "status": status,
            "gaps": gaps,
        })

    issues: list[dict[str, str]] = []
    if not objectives:
        issues.append({"severity": "critical", "message": "No specific research objectives are saved in the project logic record."})
    if objectives and len(questions) < len(objectives):
        issues.append({
            "severity": "important",
            "message": f"{len(objectives) - len(questions)} objective(s) do not yet have a corresponding research question.",
        })
    if hypotheses_expected and len(hypotheses) < len(objectives):
        issues.append({
            "severity": "important",
            "message": f"{len(objectives) - len(hypotheses)} quantitative/mixed-method objective(s) do not yet have a corresponding hypothesis. Use hypotheses only where substantively appropriate.",
        })
    if not variables:
        issues.append({"severity": "important", "message": "Key constructs or variables have not been saved for cross-chapter consistency checks."})
    if source_count < 8 and any(item["status"] != "not_started" for item in chapter_status[:2]):
        issues.append({"severity": "important", "message": "The attached source bank is still small for evidence-grounded chapter development."})
    if chapter4.strip() and objectives:
        missing_results = [row["objective_number"] for row in matrix if not row["result_covered"]]
        if missing_results:
            issues.append({
                "severity": "critical",
                "message": "Chapter Four does not clearly trace to objective(s): " + ", ".join(map(str, missing_results)) + ".",
            })
    if chapter5.strip() and objectives:
        missing_conclusions = [row["objective_number"] for row in matrix if not row["conclusion_covered"]]
        if missing_conclusions:
            issues.append({
                "severity": "critical",
                "message": "Chapter Five does not clearly trace to objective(s): " + ", ".join(map(str, missing_conclusions)) + ".",
            })

    # Heuristic progress indicators. They describe workflow readiness, not academic quality.
    profile_points = 0
    profile_points += 15 if title else 0
    profile_points += 20 if objectives else 0
    profile_points += 10 if questions else 0
    profile_points += 10 if variables else 0
    profile_points += 10 if len(context) >= 40 else 0
    profile_points += 5 if approach else 0
    profile_points += 5 if data_type else 0
    profile_score = round(profile_points / 75 * 100) if profile_points else 0

    developed_count = sum(1 for item in chapter_status if item["status"] == "developed")
    started_count = sum(1 for item in chapter_status if item["status"] == "started")
    chapter_progress = round(((developed_count + 0.45 * started_count) / max(len(chapter_status), 1)) * 100)

    alignment_components: list[float] = []
    if objectives:
        alignment_components.append(min(len(questions) / len(objectives), 1.0))
        if hypotheses_expected:
            alignment_components.append(min(len(hypotheses) / len(objectives), 1.0))
        if chapter4.strip():
            alignment_components.append(sum(1 for row in matrix if row["result_covered"]) / len(matrix))
        if chapter5.strip():
            alignment_components.append(sum(1 for row in matrix if row["conclusion_covered"]) / len(matrix))
    alignment_score = round((sum(alignment_components) / len(alignment_components)) * 100) if alignment_components else 0

    compliance_values: list[float] = []
    for value in checks.values() if isinstance(checks, dict) else []:
        if isinstance(value, dict) and isinstance(value.get("score_percent"), (int, float)):
            compliance_values.append(float(value["score_percent"]))
    compliance_score = round(sum(compliance_values) / len(compliance_values), 1) if compliance_values else None

    evidence_score = min(100, round(source_count / 30 * 100)) if source_count else 0
    readiness = round(
        profile_score * 0.30
        + chapter_progress * 0.35
        + alignment_score * 0.20
        + evidence_score * 0.10
        + ((compliance_score if compliance_score is not None else 0) * 0.05)
    )

    next_chapter = next((item for item in chapter_status if item["status"] == "not_started"), None)
    if not objectives:
        next_action = {
            "type": "project_logic",
            "label": "Add specific research objectives",
            "message": "Save the specific objectives before developing later chapters so ProjectReady can trace the whole study.",
            "chapter_number": 1,
        }
    elif not questions:
        next_action = {
            "type": "project_logic",
            "label": "Add research questions",
            "message": "Map each objective to a research question before continuing the project.",
            "chapter_number": 1,
        }
    elif source_count < 8 and not drafts.get("2"):
        next_action = {
            "type": "sources",
            "label": "Build the evidence base",
            "message": "Attach a focused set of relevant scholarly sources before developing the literature review.",
            "chapter_number": 2,
        }
    elif next_chapter:
        next_action = {
            "type": "chapter",
            "label": f"Develop Chapter {next_chapter['chapter_number']}",
            "message": f"Continue with {next_chapter['chapter_title']} using the saved project logic and earlier chapter context.",
            "chapter_number": next_chapter["chapter_number"],
        }
    elif issues:
        next_action = {
            "type": "audit",
            "label": "Resolve research alignment issues",
            "message": issues[0]["message"],
            "chapter_number": 4 if "Chapter Four" in issues[0]["message"] else 5 if "Chapter Five" in issues[0]["message"] else 1,
        }
    else:
        next_action = {
            "type": "audit",
            "label": "Run final project review",
            "message": "All expected chapter drafts are present. Review alignment, compliance and supervisor corrections before final submission preparation.",
            "chapter_number": 5,
        }

    return {
        "project_id": project.get("id"),
        "project_title": title,
        "academic_level": level,
        "research_approach": approach,
        "data_type": data_type,
        "readiness_score": max(0, min(readiness, 100)),
        "readiness_label": "Project workflow readiness, not a grade",
        "profile_score": profile_score,
        "chapter_progress": chapter_progress,
        "alignment_score": alignment_score,
        "evidence_score": evidence_score,
        "compliance_score": compliance_score,
        "source_count": source_count,
        "objectives_count": len(objectives),
        "questions_count": len(questions),
        "hypotheses_count": len(hypotheses),
        "variables_count": len(variables),
        "chapter_status": chapter_status,
        "objective_matrix": matrix,
        "issues": issues[:12],
        "next_action": next_action,
    }
