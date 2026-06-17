from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from app.source_finder import search_literature_sources

MAX_SOURCE_CONTEXT = 14

_RETRACTION_TERMS = re.compile(
    r"\b(retracted|retraction\s+notice|withdrawn|removed\s+article|expression\s+of\s+concern|erratum\s+to\s+retracted)\b",
    flags=re.IGNORECASE,
)


def _safe_get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _looks_retracted(src: dict[str, Any]) -> bool:
    """Conservative local guard, even if the main source_finder is not yet patched."""
    fields = [
        src.get("title"),
        src.get("type"),
        src.get("subtype"),
        src.get("status"),
        src.get("publication_status"),
        src.get("update_type"),
        src.get("relation_type"),
        src.get("abstract"),
    ]
    combined = " ".join(str(x or "") for x in fields)
    if _RETRACTION_TERMS.search(combined):
        return True
    flags = [
        "is_retracted",
        "retracted",
        "has_retraction",
        "is_withdrawn",
        "withdrawn",
        "removed",
        "expression_of_concern",
    ]
    return any(bool(src.get(flag)) for flag in flags)


def _select_topic_model(level: str) -> str:
    level_l = (level or "").strip().lower()
    if any(token in level_l for token in ["phd", "doctor", "dba", "ded", "professional doctorate"]):
        return os.getenv("OPENAI_TOPIC_IDEA_DOCTORAL_MODEL", os.getenv("OPENAI_DOCTORAL_DRAFT_MODEL", "gpt-5.5")).strip()
    if "research masters" in level_l or "mphil" in level_l:
        return os.getenv("OPENAI_TOPIC_IDEA_RESEARCH_MODEL", os.getenv("OPENAI_RESEARCH_MASTERS_DRAFT_MODEL", "gpt-5.5")).strip()
    return os.getenv("OPENAI_TOPIC_IDEA_MODEL", os.getenv("OPENAI_BACHELOR_DRAFT_MODEL", "gpt-5.4")).strip()


def _build_topic_search_profile(payload: dict[str, Any]) -> dict[str, Any]:
    objectives = []
    for item in str(payload.get("keywords") or "").split("\n"):
        item = item.strip(" -;,")
        if item:
            objectives.append(item)
    return {
        "title": str(payload.get("research_area") or "").strip(),
        "research_area": str(payload.get("research_area") or "").strip(),
        "study_context": str(payload.get("context") or "").strip(),
        "level": str(payload.get("level") or "Bachelors"),
        "research_approach": str(payload.get("methodology") or "Not specified"),
        "data_type": str(payload.get("data_type") or "Not specified"),
        "objectives": objectives[:5],
        "notes": str(payload.get("country_region") or "").strip(),
    }


def _source_context(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context = []
    for idx, src in enumerate(sources[:MAX_SOURCE_CONTEXT], start=1):
        context.append({
            "key": f"S{idx}",
            "title": src.get("title", ""),
            "authors": src.get("authors", []),
            "year": src.get("year", ""),
            "source": src.get("source", ""),
            "doi": src.get("doi", ""),
            "url": src.get("url", ""),
            "abstract": str(src.get("abstract") or "")[:900],
            "database": src.get("database", ""),
            "citation_count": src.get("citation_count", ""),
        })
    return context


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _fallback_ideas(payload: dict[str, Any], sources: list[dict[str, Any]], count: int) -> dict[str, Any]:
    area = str(payload.get("research_area") or "the selected research area").strip() or "the selected research area"
    context = str(payload.get("context") or payload.get("country_region") or "the selected context").strip() or "the selected context"
    methodology = str(payload.get("methodology") or "mixed or appropriate methodology").strip()
    trends = []
    for src in sources[:6]:
        title = str(src.get("title") or "").strip()
        year = src.get("year") or "n.d."
        if title:
            trends.append(f"{title} ({year})")
    if not trends:
        trends = ["Recent literature search did not return enough verified metadata. Refine the topic keywords and rerun the idea search."]

    ideas = []
    stems = [
        "Emerging Determinants of",
        "Institutional and Behavioural Drivers of",
        "Digital, Governance and Contextual Factors Shaping",
        "A Context-Sensitive Analysis of",
        "Evidence, Practice and Outcomes in",
        "Barriers, Enablers and Performance Implications of",
    ]
    for i in range(max(1, count)):
        stem = stems[i % len(stems)]
        ideas.append({
            "title": f"{stem} {area} in {context}",
            "synopsis": (
                f"This study would examine how recent developments in {area} are shaping outcomes in {context}. "
                f"It would use {methodology.lower()} and focus on the empirical gap suggested by recent source-search results."
            ),
            "current_research_trend_or_gap": trends[i % len(trends)],
            "possible_methodology": methodology,
            "possible_variables_or_constructs": [area, "contextual drivers", "outcomes", "institutional factors"],
            "possible_data_sources": ["recent scholarly literature", "survey or interview data", "official or institutional records where available"],
            "potential_contribution": "Provides a current, context-specific study that can be refined once the supervisor confirms the final scope and available data.",
            "evidence_sources": ["S1", "S2"] if len(sources) >= 2 else (["S1"] if sources else []),
            "attention_note": "[confirm final scope, variables and data access before approval]",
        })
    return {
        "trend_summary": "Fallback topic ideas were generated from the search query and available source metadata. Refine the search terms for stronger trend grounding.",
        "ideas": ideas,
        "suggested_next_step": "Select one title, rerun the source finder with its key terms, then convert it into objectives and research questions.",
    }


def generate_topic_ideas(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate thesis/dissertation title ideas grounded in recent source-search metadata."""
    max_ideas = max(3, min(int(payload.get("max_ideas") or 8), 12))
    profile = _build_topic_search_profile(payload)
    search_terms = " ".join([
        str(payload.get("research_area") or ""),
        str(payload.get("context") or ""),
        str(payload.get("country_region") or ""),
        str(payload.get("keywords") or ""),
        str(payload.get("trend_focus") or ""),
    ])
    search_result = search_literature_sources(
        profile=profile,
        query=search_terms,
        max_results=max(10, min(max_ideas * 3, 30)),
        include_older_foundational=bool(payload.get("include_older_foundational", True)),
    )
    raw_sources = search_result.get("sources") or []
    usable_sources = [src for src in raw_sources if not _looks_retracted(src)]
    excluded_retracted = [src for src in raw_sources if _looks_retracted(src)]

    model = _select_topic_model(profile.get("level", ""))
    client = _safe_get_openai_client()

    if not client or os.getenv("PROJECTREADY_TOPIC_IDEAS_USE_AI", "1").strip().lower() in {"0", "false", "no"}:
        generated = _fallback_ideas(payload, usable_sources, max_ideas)
        source_mode = "metadata_fallback"
    else:
        idea_prompt = {
            "task": "Generate thesis or dissertation title ideas and brief synopses grounded in current source-search metadata.",
            "user_inputs": payload,
            "rules": [
                "Use the retrieved source titles, abstracts, years and venues to infer current research trends and gaps.",
                "Do not invent citations, papers, datasets, institutional facts, statistics or trend claims.",
                "Do not use retracted, withdrawn, removed or expression-of-concern sources for any idea or argument.",
                "Do not copy source titles. Create original, researchable thesis/dissertation titles.",
                "Adapt sophistication to the selected academic level. Bachelor topics should be feasible; doctoral topics should show stronger originality and contribution.",
                "Each idea must include a concise synopsis, trend/gap, possible methodology, variables/constructs, possible data sources, contribution and evidence source keys.",
                "Return JSON only with keys: trend_summary, ideas, suggested_next_step.",
                "Each idea object must contain: title, synopsis, current_research_trend_or_gap, possible_methodology, possible_variables_or_constructs, possible_data_sources, potential_contribution, evidence_sources, attention_note.",
                "If evidence is thin, say so in the attention_note rather than overstating the trend.",
            ],
            "source_records": _source_context(usable_sources),
            "requested_number_of_ideas": max_ideas,
            "current_year": datetime.now().year,
        }
        try:
            response = client.responses.create(
                model=model,
                instructions=(
                    "You are ProjectReady AI's thesis topic adviser. Produce feasible, original, evidence-grounded thesis/dissertation ideas. "
                    "Use only the supplied search metadata. Exclude retracted or suspect sources. Return clean JSON only."
                ),
                input=json.dumps(idea_prompt, ensure_ascii=False, indent=2),
            )
            parsed = _extract_json(str(getattr(response, "output_text", "") or ""))
            if parsed and isinstance(parsed.get("ideas"), list):
                generated = parsed
                source_mode = f"ai:{model}"
            else:
                generated = _fallback_ideas(payload, usable_sources, max_ideas)
                source_mode = "metadata_fallback_parse_error"
        except Exception as exc:
            generated = _fallback_ideas(payload, usable_sources, max_ideas)
            generated["attention"] = f"AI idea generation failed and fallback ideas were used: {str(exc)[:180]}"
            source_mode = "metadata_fallback_ai_error"

    return {
        "query": search_result.get("query", ""),
        "searched_at": search_result.get("searched_at", ""),
        "recent_reference_window": search_result.get("recent_reference_window", ""),
        "databases": search_result.get("databases", []),
        "source_mode": source_mode,
        "excluded_retracted_count": len(excluded_retracted),
        "excluded_retracted_titles": [src.get("title") for src in excluded_retracted[:8] if src.get("title")],
        "trend_summary": generated.get("trend_summary", ""),
        "ideas": generated.get("ideas", [])[:max_ideas],
        "suggested_next_step": generated.get("suggested_next_step", ""),
        "source_records_used": _source_context(usable_sources),
        "provider_errors": search_result.get("provider_errors", []),
        "usage_note": (
            "Ideas are grounded in retrieved metadata and should be verified with a supervisor and a full literature search before submission. "
            "Retracted or withdrawn records are excluded from the idea-generation context where detected."
        ),
    }
