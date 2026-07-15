from __future__ import annotations

import os
import re
from typing import Any

from app.source_finder import search_literature_sources


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _source_key(source: dict[str, Any]) -> str:
    doi = _normalise(source.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9]+", "", _normalise(source.get("title")).lower())[:120]
    return f"title:{title}" if title else ""


def _merge_sources(*collections: list[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        for source in collection or []:
            if not isinstance(source, dict):
                continue
            key = _source_key(source)
            if not key or key in seen:
                continue
            tier = str(source.get("relevance_tier") or "").strip()
            if tier == "not_relevant":
                continue
            seen.add(key)
            merged.append(dict(source))
            if len(merged) >= limit:
                return merged
    return merged


def _level_key(profile: dict[str, Any]) -> str:
    value = _normalise(profile.get("level")).lower()
    if "phd" in value:
        return "phd"
    if any(token in value for token in ("professional doctorate", "dba", "ded")):
        return "professional_doctorate"
    if "research masters" in value or "mphil" in value:
        return "research_masters"
    if "non-research" in value or "non research" in value:
        return "nonresearch_masters"
    return "bachelors"


_AUTO_SOURCE_MINIMUMS: dict[str, dict[int, int]] = {
    "bachelors": {1: 12, 2: 24, 3: 8, 4: 10, 5: 6},
    "nonresearch_masters": {1: 15, 2: 30, 3: 10, 4: 12, 5: 8},
    "research_masters": {1: 18, 2: 40, 3: 14, 4: 16, 5: 10},
    "professional_doctorate": {1: 20, 2: 48, 3: 18, 4: 20, 5: 12},
    "phd": {1: 24, 2: 60, 3: 22, 4: 28, 5: 16},
}


def _existing_sources(profile: dict[str, Any]) -> list[dict[str, Any]]:
    bank = profile.get("source_bank") or []
    if not isinstance(bank, list):
        bank = []
    retrieved = profile.get("retrieved_sources") or {}
    retrieved_sources = retrieved.get("sources") or [] if isinstance(retrieved, dict) else []
    if not isinstance(retrieved_sources, list):
        retrieved_sources = []
    return _merge_sources(bank, retrieved_sources)


def _query_candidates(profile: dict[str, Any], chapter_number: int) -> list[str]:
    title = _normalise(profile.get("title"))
    research_area = _normalise(profile.get("research_area"))
    context = _normalise(profile.get("study_context"))
    supplied_query = _normalise(profile.get("source_search_terms"))
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [line.strip() for line in re.split(r"\n|;", objectives) if line.strip()]
    objective_text = _normalise(" ".join(str(item) for item in objectives[:2]))
    variables = profile.get("variables") or {}
    variable_text = _normalise(variables.get("raw_variables") if isinstance(variables, dict) else variables)

    candidates = [supplied_query, title]
    concept_query = " ".join(part for part in [research_area, variable_text, context] if part)
    if concept_query:
        candidates.append(concept_query)
    if objective_text:
        candidates.append(objective_text)

    # Keep searches concept-led. Chapter labels are added only to direct the evidence type.
    suffixes = {
        1: "context problem evidence",
        2: "theory empirical studies",
        3: "research method measurement validation",
        4: "empirical findings discussion",
        5: "implications recommendations",
    }
    suffix = suffixes.get(int(chapter_number or 0), "")
    output: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _normalise(candidate)
        if not cleaned:
            continue
        if suffix and cleaned != supplied_query:
            cleaned = f"{cleaned} {suffix}"
        cleaned = cleaned[:220]
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def ensure_automatic_source_support(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    """Enrich a thin evidence bank before drafting, without blocking on provider failure.

    This is deliberately conservative. It searches only when the project has fewer
    relevant source records than the level/chapter minimum. Retrieved records still
    pass the source finder's relevance gate, and the writing model is instructed to
    cite only records that directly support the claim.
    """
    if not _env_bool("PROJECTREADY_AUTO_SOURCE_SUPPORT", True):
        return {"enabled": False, "searched": False, "reason": "automatic source support disabled"}
    if profile.get("automatic_source_support") is False:
        return {"enabled": False, "searched": False, "reason": "disabled for this project"}

    existing = _existing_sources(profile)
    minimum = _AUTO_SOURCE_MINIMUMS.get(_level_key(profile), {}).get(int(chapter_number or 0), 10)
    minimum = max(6, int(os.getenv("PROJECTREADY_AUTO_SOURCE_MINIMUM_OVERRIDE", "0") or 0) or minimum)
    if len(existing) >= minimum:
        return {
            "enabled": True,
            "searched": False,
            "reason": "existing evidence bank is sufficient",
            "source_count": len(existing),
            "minimum_source_target": minimum,
        }

    query_limit = max(1, min(3, int(os.getenv("PROJECTREADY_AUTO_SOURCE_QUERY_COUNT", "2") or 2)))
    max_results = max(8, min(30, int(os.getenv("PROJECTREADY_AUTO_SOURCE_RESULTS_PER_QUERY", "14") or 14)))
    queries = _query_candidates(profile, chapter_number)[:query_limit]
    gathered: list[dict[str, Any]] = []
    provider_errors: list[dict[str, str]] = []
    databases: list[str] = []

    for query in queries:
        try:
            result = search_literature_sources(
                profile=profile,
                query=query,
                max_results=max_results,
                include_older_foundational=True,
                use_relevance_gate=True,
                attach_not_relevant_sources=False,
            )
        except Exception as exc:
            provider_errors.append({"provider": "automatic source support", "error": str(exc)[:220]})
            continue
        gathered.extend(result.get("sources") or [])
        provider_errors.extend(result.get("provider_errors") or [])
        for database in result.get("databases") or []:
            if database not in databases:
                databases.append(database)

    merged = _merge_sources(existing, gathered)
    if merged:
        profile["source_bank"] = merged
        current = profile.get("retrieved_sources") or {}
        if not isinstance(current, dict):
            current = {}
        profile["retrieved_sources"] = {
            **current,
            "query": " | ".join(queries),
            "databases": databases,
            "provider_errors": provider_errors,
            "sources": merged,
            "source_bank_count": len(merged),
            "automatic": True,
            "usage_note": (
                "Automatically retrieved records are candidates only. Cite a record only when its metadata or abstract "
                "directly supports the claim, and verify the final reference before submission."
            ),
        }

    summary = {
        "enabled": True,
        "searched": bool(queries),
        "queries": queries,
        "source_count_before": len(existing),
        "source_count_after": len(merged),
        "minimum_source_target": minimum,
        "provider_errors": provider_errors,
        "databases": databases,
    }
    profile["automatic_source_support_summary"] = summary
    return summary
