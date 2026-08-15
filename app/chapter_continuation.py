from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.citation_matrix import citation_target
from app.provisional_statistics import refresh_provisional_statistics
from app.template_store import get_chapter, selected_sections


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _variable_list(profile: dict[str, Any]) -> list[str]:
    variables = profile.get("variables") or {}
    if isinstance(variables, dict):
        raw = variables.get("raw_variables") or []
        return _list(raw)
    return _list(variables)


def chapter_selection_is_complete(completed_chapter: int, selected_section_ids: list[str] | None) -> bool:
    """Return True only when the saved generation covered the full standard chapter."""
    try:
        expected_sections = selected_sections(int(completed_chapter), [])
    except Exception:
        return False
    expected = {
        str(section.get("section_id") or "").strip()
        for section in expected_sections
        if str(section.get("section_id") or "").strip()
    }
    if not expected:
        return False
    selected = {str(item).strip() for item in (selected_section_ids or []) if str(item).strip()}
    return expected.issubset(selected)


def continuation_requirements(profile: dict[str, Any], next_chapter: int) -> list[dict[str, str]]:
    required: list[dict[str, str]] = []
    if not _text(profile.get("title")):
        required.append({"field": "title", "label": "Research title", "reason": "Confirm the approved or current title before continuing."})
    if not _list(profile.get("objectives")):
        required.append({"field": "objectives", "label": "Research objectives", "reason": "Later chapters must remain linked to the approved objectives."})
    if int(next_chapter or 0) >= 2 and not _list(profile.get("research_questions")):
        required.append({"field": "research_questions", "label": "Research questions", "reason": "Confirm or add the questions that the literature and later analysis should address."})
    if int(next_chapter or 0) in {2, 3, 4} and not _variable_list(profile):
        required.append({"field": "variables_constructs", "label": "Variables or constructs", "reason": "Confirm the main variables, constructs or concepts used across chapters."})
    if int(next_chapter or 0) >= 3 and not _text(profile.get("research_approach")):
        required.append({"field": "research_approach", "label": "Research approach", "reason": "Methodology and analysis need a confirmed research approach."})
    if int(next_chapter or 0) == 4:
        uploaded = profile.get("uploaded_results") or {}
        if not isinstance(uploaded, dict) or not uploaded:
            required.append({"field": "results", "label": "Actual results/output", "reason": "Chapter Four must use actual analysis output rather than invented findings."})
    return required


def build_chapter_linkage(profile: dict[str, Any], completed_chapter: int, *, draft_version: dict[str, Any] | None = None, draft_text: str = "") -> dict[str, Any]:
    expected = max(1, int(profile.get("expected_chapters") or 5))
    next_chapter = int(completed_chapter or 0) + 1
    if completed_chapter <= 0 or next_chapter > expected or next_chapter > 7:
        return {"available": False, "completed_chapter": int(completed_chapter or 0)}
    try:
        next_template = get_chapter(next_chapter)
        next_title = str(next_template.get("chapter_title") or f"Chapter {next_chapter}")
    except Exception:
        next_title = f"Chapter {next_chapter}"

    citation = citation_target(profile, next_chapter, chapter_type=next_title)
    provisional = refresh_provisional_statistics(profile)
    draft_value = str(draft_text or "")
    if draft_value:
        for item in provisional:
            item["used_in_completed_chapter"] = bool(
                str(item.get("statement") or "").strip()
                and str(item.get("statement") or "").strip() in draft_value
            )
        provisional_for_confirmation = [
            item for item in provisional
            if item.get("status") != "rejected" and item.get("used_in_completed_chapter")
        ]
    else:
        provisional_for_confirmation = [item for item in provisional if item.get("status") != "rejected"]
    needs = continuation_requirements(profile, next_chapter)
    linkage = {
        "available": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_chapter": int(completed_chapter),
        "next_chapter": next_chapter,
        "next_chapter_title": next_title,
        "title": _text(profile.get("title")),
        "objectives": _list(profile.get("objectives")),
        "research_questions": _list(profile.get("research_questions")),
        "hypotheses": _list(profile.get("hypotheses")),
        "variables": _variable_list(profile),
        "research_approach": _text(profile.get("research_approach")),
        "study_context": _text(profile.get("study_context")),
        "draft_version_id": str((draft_version or {}).get("id") or ""),
        "citation_target": citation,
        "needs_confirmation": needs,
        "provisional_statistics": provisional_for_confirmation,
        "automatic_alignment": (
            f"Chapter {completed_chapter} has been saved as alignment context for Chapter {next_chapter}. "
            "ProjectReady will carry forward the approved title, objectives, questions, hypotheses, variables, terminology and study context."
        ),
    }
    return linkage


def store_chapter_linkage(profile: dict[str, Any], linkage: dict[str, Any]) -> None:
    if not linkage.get("available"):
        return
    links = profile.get("chapter_linkages") or {}
    if not isinstance(links, dict):
        links = {}
    key = f"{linkage.get('completed_chapter')}->{linkage.get('next_chapter')}"
    links[key] = linkage
    profile["chapter_linkages"] = links
