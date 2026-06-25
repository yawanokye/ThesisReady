from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from app.source_finder import search_literature_sources
from app.research_resource_finder import discover_research_resources

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



def _level_key(level: str) -> str:
    level_l = (level or "").strip().lower()
    if "phd" in level_l:
        return "phd"
    if any(token in level_l for token in ["professional doctorate", "dba", "ded", "doctorate"]):
        return "professional_doctorate"
    if "non-research masters" in level_l or "non research masters" in level_l:
        return "non_research_masters"
    if "research masters" in level_l or "mphil" in level_l:
        return "research_masters"
    return "bachelors"


def _objective_requirement(level: str) -> dict[str, Any]:
    key = _level_key(level)
    profiles: dict[str, dict[str, Any]] = {
        "bachelors": {
            "specific_count": 4,
            "label": "Bachelors",
            "guidance": (
                "Keep the study feasible and clearly bounded. Include descriptive, relational and practical objectives "
                "that can be completed with accessible data and standard undergraduate methods."
            ),
        },
        "non_research_masters": {
            "specific_count": 4,
            "label": "Non-Research Masters",
            "guidance": (
                "Use applied analytical objectives that diagnose the problem, evaluate important influences, compare "
                "relevant groups or practices and support implementable recommendations."
            ),
        },
        "research_masters": {
            "specific_count": 5,
            "label": "Research Masters / MPhil",
            "guidance": (
                "Use theory-grounded objectives that support construct definition, direct-effect testing, mechanisms or "
                "boundary conditions where justified, robustness assessment and a defensible empirical contribution."
            ),
        },
        "professional_doctorate": {
            "specific_count": 5,
            "label": "Professional Doctorate / DBA / DEd",
            "guidance": (
                "Use advanced applied objectives that diagnose a significant practice problem, test mechanisms, evaluate "
                "current practice or policy, develop an evidence-informed solution and assess its implementation value."
            ),
        },
        "phd": {
            "specific_count": 6,
            "label": "PhD",
            "guidance": (
                "Use original, theory-building or theory-extending objectives that address mechanisms, boundary conditions, "
                "heterogeneity or temporal or multilevel complexity where appropriate, and culminate in a validated scholarly contribution."
            ),
        },
    }
    return profiles[key]


def _normalise_objective_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -;,.\t\n")
    if not text:
        return ""
    if not re.match(r"^to\b", text, flags=re.IGNORECASE):
        text = f"To {text[0].lower() + text[1:] if len(text) > 1 else text.lower()}"
    return text.rstrip(".;") + "."


def _fallback_objectives(payload: dict[str, Any], idea: dict[str, Any]) -> dict[str, Any]:
    level = str(payload.get("level") or "Bachelors")
    profile = _objective_requirement(level)
    key = _level_key(level)
    area = str(payload.get("research_area") or "the selected research problem").strip()
    topic_focus = str(idea.get("title") or area).strip()
    context = str(payload.get("context") or payload.get("country_region") or "the selected study context").strip()
    methodology = str(payload.get("methodology") or "an appropriate methodology").strip()

    constructs = idea.get("possible_variables_or_constructs") or []
    if not isinstance(constructs, list):
        constructs = [constructs]
    constructs = [str(item).strip() for item in constructs if str(item).strip()]
    focal = constructs[0] if constructs else area
    driver = constructs[1] if len(constructs) > 1 else "the principal explanatory factors"
    outcome = constructs[2] if len(constructs) > 2 else "the principal study outcomes"
    context_factor = constructs[3] if len(constructs) > 3 else "relevant contextual and institutional conditions"

    if key == "bachelors":
        general = f"To examine {topic_focus}"
        specifics = [
            f"To assess the current pattern or level of {focal} in {context}",
            f"To examine the relationship between {driver} and {outcome} in {context}",
            f"To identify the main barriers and enabling conditions associated with {area} in {context}",
            f"To propose practical recommendations for improving {outcome} based on the study findings",
        ]
    elif key == "non_research_masters":
        general = f"To evaluate {topic_focus} and its practical implications"
        specifics = [
            f"To diagnose the current state of {focal} and {outcome} in {context}",
            f"To analyse the influence of {driver} and {context_factor} on {outcome}",
            f"To compare relevant groups, settings or organisational practices in relation to {area}",
            f"To develop evidence-based recommendations that can improve practice, policy or managerial decision-making in {context}",
        ]
    elif key == "research_masters":
        general = f"To develop and empirically test an explanatory account of {topic_focus} using {methodology.lower()}"
        specifics = [
            f"To define and operationalise the central constructs associated with {area} for the study context",
            f"To test the direct relationships among {focal}, {driver} and {outcome}",
            f"To examine the mechanisms or boundary conditions through which {context_factor} shapes the focal relationships, where theoretically justified",
            f"To assess the robustness of the findings across relevant groups, model specifications or data conditions",
            f"To refine the explanatory model and derive theoretical and empirical implications for {context}",
        ]
    elif key == "professional_doctorate":
        general = f"To develop and validate an evidence-informed framework for addressing {topic_focus}"
        specifics = [
            f"To diagnose the scale, consequences and organisational context of the practice problem associated with {area}",
            f"To test the behavioural, institutional or managerial mechanisms linking {driver} to {outcome}",
            f"To evaluate the adequacy of existing policies, strategies or professional practices used to address the problem",
            f"To develop an evidence-informed intervention, decision framework or practice model suited to {context}",
            f"To assess the proposed solution's feasibility, stakeholder acceptability and likely implementation value",
        ]
    else:
        general = f"To develop and rigorously test an original explanatory framework for {topic_focus}"
        specifics = [
            f"To critically synthesise and extend the theoretical foundations of {area} for the study context",
            f"To develop or validate rigorous measures and operational definitions for the central constructs",
            f"To estimate the direct and indirect mechanisms linking {focal}, {driver} and {outcome}",
            f"To test theoretically defensible moderators, boundary conditions or contextual contingencies involving {context_factor}",
            f"To examine heterogeneity, temporal dynamics, multilevel structure or alternative explanations where supported by the design and data",
            f"To validate the proposed framework and specify its original theoretical, methodological and practical contribution",
        ]

    return {
        "general_objective": _normalise_objective_text(general),
        "specific_objectives": [_normalise_objective_text(item) for item in specifics[: profile["specific_count"]]],
        "level_alignment": f'{profile["label"]}: {profile["guidance"]}',
    }


def _ensure_level_appropriate_objectives(
    payload: dict[str, Any],
    idea: dict[str, Any],
) -> dict[str, Any]:
    """Guarantee one general objective and enough level-appropriate specific objectives for every idea."""
    fallback = _fallback_objectives(payload, idea)
    raw = idea.get("proposed_objectives")

    general = ""
    specifics: list[Any] = []
    level_alignment = ""

    if isinstance(raw, dict):
        general = _normalise_objective_text(
            raw.get("general_objective")
            or raw.get("general")
            or raw.get("overall_objective")
        )
        raw_specifics = (
            raw.get("specific_objectives")
            or raw.get("specific")
            or raw.get("objectives")
            or []
        )
        specifics = raw_specifics if isinstance(raw_specifics, list) else [raw_specifics]
        level_alignment = str(raw.get("level_alignment") or raw.get("level_note") or "").strip()
    elif isinstance(raw, list):
        specifics = raw
    elif isinstance(raw, str):
        specifics = [line for line in re.split(r"[\n;]+", raw) if line.strip()]

    general = general or fallback["general_objective"]
    cleaned_specifics: list[str] = []
    seen: set[str] = set()
    for item in specifics:
        cleaned = _normalise_objective_text(item)
        key = cleaned.lower()
        if cleaned and key not in seen and cleaned.lower() != general.lower():
            cleaned_specifics.append(cleaned)
            seen.add(key)

    required_count = int(_objective_requirement(str(payload.get("level") or "Bachelors"))["specific_count"])
    for item in fallback["specific_objectives"]:
        key = item.lower()
        if len(cleaned_specifics) >= required_count:
            break
        if key not in seen and key != general.lower():
            cleaned_specifics.append(item)
            seen.add(key)

    idea["proposed_objectives"] = {
        "general_objective": general,
        "specific_objectives": cleaned_specifics[:required_count],
        "level_alignment": level_alignment or fallback["level_alignment"],
    }
    return idea

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
        idea = {
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
        }
        idea["proposed_objectives"] = _fallback_objectives(payload, idea)
        ideas.append(idea)
    return {
        "trend_summary": "Fallback topic ideas were generated from the search query and available source metadata. Refine the search terms for stronger trend grounding.",
        "ideas": ideas,
        "suggested_next_step": "Select one title, refine its proposed objectives with the supervisor, rerun the source finder with its key terms, and derive aligned research questions or hypotheses.",
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
            "task": "Generate thesis or dissertation title ideas, brief synopses and level-appropriate proposed research objectives grounded in current source-search metadata.",
            "user_inputs": payload,
            "rules": [
                "Use the retrieved source titles, abstracts, years and venues to infer current research trends and gaps.",
                "Do not invent citations, papers, datasets, institutional facts, statistics or trend claims.",
                "Do not use retracted, withdrawn, removed or expression-of-concern sources for any idea or argument.",
                "Do not copy source titles. Create original, researchable thesis/dissertation titles.",
                "Adapt sophistication to the selected academic level. Bachelor topics should be feasible; doctoral topics should show stronger originality, theoretical depth and contribution.",
                "For every idea, provide one general objective and the required number of specific objectives for the selected level: Bachelors 4; Non-Research Masters 4; Research Masters/MPhil 5; Professional Doctorate 5; PhD 6.",
                "Objectives must be logically aligned with the title, synopsis, variables, methodology and likely data. Do not add mediation, moderation, causal, longitudinal, multilevel, intervention or measurement-validation objectives unless the selected level, design and data direction can reasonably support them.",
                "Bachelor objectives should cover feasible description, relationships, barriers or enablers and practical implications. Non-Research Masters objectives should be applied and evaluative. Research Masters/MPhil objectives should be theory-grounded and analytically rigorous. Professional Doctorate objectives should diagnose practice and develop or evaluate an implementable solution. PhD objectives should support theory extension or development, mechanisms, boundary conditions and validation of an original contribution.",
                "Each idea must include a concise synopsis, trend/gap, possible methodology, variables/constructs, broad data-source categories, contribution, proposed objectives and evidence source keys.",
                "Do not invent named datasets, questionnaires, scales or instruments. The application will run a separate live resource search after the ideas are generated.",
                "Return JSON only with keys: trend_summary, ideas, suggested_next_step.",
                "Each idea object must contain: title, synopsis, current_research_trend_or_gap, possible_methodology, possible_variables_or_constructs, possible_data_sources, potential_contribution, proposed_objectives, evidence_sources, attention_note.",
                "proposed_objectives must be an object with: general_objective, specific_objectives and level_alignment.",
                "If evidence is thin, say so in the attention_note rather than overstating the trend.",
            ],
            "source_records": _source_context(usable_sources),
            "requested_number_of_ideas": max_ideas,
            "objective_requirement": _objective_requirement(profile.get("level", "Bachelors")),
            "current_year": datetime.now().year,
        }
        try:
            response = client.responses.create(
                model=model,
                instructions=(
                    "You are ProjectReady AI's thesis topic adviser. Produce feasible, original, evidence-grounded thesis/dissertation ideas with objectives matched to the selected academic level. "
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

    processed_ideas: list[dict[str, Any]] = []
    for raw_idea in (generated.get("ideas") or [])[:max_ideas]:
        if not isinstance(raw_idea, dict):
            continue
        processed_ideas.append(_ensure_level_appropriate_objectives(payload, dict(raw_idea)))

    resource_result = discover_research_resources(payload, processed_ideas)
    processed_ideas = resource_result.get("ideas") or processed_ideas
    resource_search = resource_result.get("resource_search") or {}

    return {
        "query": search_result.get("query", ""),
        "searched_at": search_result.get("searched_at", ""),
        "recent_reference_window": search_result.get("recent_reference_window", ""),
        "databases": search_result.get("databases", []),
        "source_mode": source_mode,
        "selected_level": profile.get("level", "Bachelors"),
        "excluded_retracted_count": len(excluded_retracted),
        "excluded_retracted_titles": [src.get("title") for src in excluded_retracted[:8] if src.get("title")],
        "trend_summary": generated.get("trend_summary", ""),
        "ideas": processed_ideas,
        "suggested_next_step": generated.get("suggested_next_step", ""),
        "source_records_used": _source_context(usable_sources),
        "provider_errors": (search_result.get("provider_errors", []) + (resource_search.get("provider_errors") or [])),
        "resource_search": resource_search,
        "usage_note": (
            "Ideas are grounded in retrieved metadata and should be verified with a supervisor and a full literature search before submission. "
            "Retracted or withdrawn records are excluded from the idea-generation context where detected. "
            "Named datasets and instrument sources are candidates from live metadata searches or official source catalogues and must be checked before adoption, adaptation or analysis."
        ),
    }
