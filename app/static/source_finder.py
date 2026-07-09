from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from html import unescape
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 12
MAX_QUERY_CHARS = 220
MAX_ABSTRACT_CHARS = 650
RETRACTION_PATTERN = re.compile(r"\b(retracted|retraction|withdrawn|withdrawal|expression\s+of\s+concern|removed\s+article)\b", re.IGNORECASE)

# Terms that should not, by themselves, make a record relevant. The gate is
# intentionally lexical and transparent so it remains fast and costs nothing.
_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "between",
    "by", "for", "from", "how", "in", "into", "is", "it", "of", "on", "or",
    "that", "the", "their", "this", "to", "using", "was", "were", "what",
    "when", "where", "which", "with", "within", "without",
}
_GENERIC_RESEARCH_TERMS = {
    "analysis", "approach", "assessment", "association", "case", "comparative",
    "context", "determinant", "determinants", "effect", "effects", "empirical",
    "evidence", "examine", "examining", "factor", "factors", "findings", "impact",
    "impacts", "influence", "investigate", "investigation", "relationship", "research",
    "role", "study", "studies", "towards", "trend", "trends",
}
_POPULATION_CONTEXT_TERMS = {
    "adult", "adults", "adolescent", "adolescents", "among", "company", "companies",
    "employee", "employees", "firm", "firms", "household", "households", "informal",
    "institution", "institutions", "organisation", "organisations", "organization",
    "organizations", "participant", "participants", "postgraduate", "postgraduates",
    "respondent", "respondents", "sector", "sectors", "student", "students", "teacher",
    "teachers", "undergraduate", "undergraduates", "worker", "workers",
    "women", "youth",
}
_GEOGRAPHIC_TERMS = {
    "africa", "african", "asia", "asian", "europe", "european", "global",
    "ghana", "ghanaian", "nigeria", "nigerian", "kenya", "kenyan", "uganda",
    "ugandan", "tanzania", "tanzanian", "rwanda", "rwandan", "ethiopia",
    "ethiopian", "zambia", "zambian", "zimbabwe", "zimbabwean", "botswana",
    "cameroon", "colombia", "china", "india", "indonesia", "malaysia", "uk",
    "usa", "united", "states", "kingdom", "sub", "saharan",
}
_EDUCATION_TERMS = {
    "academic", "classroom", "college", "curriculum", "education", "educational",
    "learning", "learner", "learners", "literacy", "pedagogy", "school", "schools",
    "student", "students", "teacher", "teachers", "teaching", "university",
}


def _normalise_search_text(value: Any) -> str:
    """Normalise metadata text while preserving meaningful compound concepts."""
    text = unescape(str(value or "")).lower()
    # Treat pass-through as one concept. Without this, an unrelated record such
    # as "class pass" can appear relevant merely because it contains "pass".
    text = re.sub(r"\bpass[\s\-‐‑‒–—]+through\b", "passthrough", text)
    text = re.sub(r"[‐‑‒–—]", "-", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenise(value: Any) -> list[str]:
    return [token for token in _normalise_search_text(value).split() if len(token) >= 3]


def _unique_phrases(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:-")
        key = _normalise_search_text(cleaned)
        if not cleaned or not key or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def build_source_query(profile: dict[str, Any], user_query: str = "") -> str:
    """Create a concise, concept-led query instead of one long profile dump.

    An explicit user query is treated as the primary search instruction. The
    title and research area are only added when they contribute new concepts.
    Objectives and context are used only when no focused query was supplied.
    """
    explicit = re.sub(r"\s+", " ", str(user_query or "")).strip()
    title = re.sub(r"\s+", " ", str(profile.get("title") or "")).strip()
    area = re.sub(r"\s+", " ", str(profile.get("research_area") or "")).strip()

    if explicit:
        # The user-entered terms are already a deliberate focused search. Do
        # not silently append the broader title, objectives or context.
        return explicit[:MAX_QUERY_CHARS]

    pieces: list[str] = _unique_phrases([title, area])
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [x.strip() for x in re.split(r"\n|;", objectives) if x.strip()]
    if not pieces and objectives:
        pieces.append(str(objectives[0]).strip())

    context = str(profile.get("study_context") or "").strip()
    if not pieces and context:
        first_sentence = re.split(r"(?<=[.!?])\s+", context)[0]
        pieces.append(first_sentence[:120])

    query = re.sub(r"\s+", " ", " ".join(_unique_phrases(pieces))).strip()
    return query[:MAX_QUERY_CHARS]

def search_literature_sources(
    profile: dict[str, Any],
    query: str = "",
    max_results: int = 30,
    include_older_foundational: bool = True,
    use_relevance_gate: bool = True,
    attach_not_relevant_sources: bool = False,
) -> dict[str, Any]:
    """Search open scholarly metadata and attach only defensibly relevant records.

    The requested result count is a ceiling, not a quota. If only nine records
    pass the relevance gate, nine are returned rather than padding the result
    with papers that merely mention the country or one generic word.
    """
    final_query = build_source_query(profile, query)
    if not final_query:
        raise ValueError(
            "Please provide a project title, research area, objective, or search terms before finding sources."
        )

    max_results = max(3, min(int(max_results or 30), 60))
    current_year = datetime.now().year
    recent_start_year = current_year - 5

    provider_specs: list[tuple[str, Any]] = [
        ("OpenAlex", _search_openalex),
        ("Crossref", _search_crossref),
        ("Semantic Scholar", _search_semantic_scholar),
    ]
    skipped_providers: list[dict[str, str]] = []
    if _query_is_education_related(final_query):
        provider_specs.append(("ERIC", _search_eric))
    else:
        skipped_providers.append({
            "provider": "ERIC",
            "reason": "Skipped because the query is not education-related.",
        })

    records: list[dict[str, Any]] = []
    provider_errors: list[dict[str, str]] = []
    searched_databases: list[str] = []
    for provider_name, provider in provider_specs:
        searched_databases.append(provider_name)
        try:
            records.extend(provider(final_query, per_provider=max(8, max_results)))
        except Exception as exc:
            provider_errors.append({"provider": provider_name, "error": str(exc)[:220]})

    safe_records: list[dict[str, Any]] = []
    excluded_retracted: list[dict[str, Any]] = []
    for record in records:
        if _is_retracted_record(record):
            excluded_retracted.append(record)
            continue
        safe_records.append(record)

    ranked = _dedupe_and_rank(
        safe_records,
        query=final_query,
        recent_start_year=recent_start_year,
    )

    relevant_records = [
        src for src in ranked
        if str(src.get("relevance_tier") or "") in {"highly_relevant", "partly_relevant"}
    ]
    rejected_irrelevant = [
        src for src in ranked
        if str(src.get("relevance_tier") or "") == "not_relevant"
    ]

    if not use_relevance_gate:
        eligible = ranked
    elif attach_not_relevant_sources:
        eligible = ranked
    else:
        eligible = relevant_records

    recent: list[dict[str, Any]] = []
    older: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []
    for src in eligible:
        year = _safe_int(src.get("year"))
        if year is None:
            undated.append(src)
        elif year >= recent_start_year:
            recent.append(src)
        else:
            older.append(src)

    if include_older_foundational:
        # Reserve room for older, highly relevant foundational work while still
        # keeping most records inside the recent-reference window.
        recent_quota = max(1, int(round(max_results * 0.75)))
        selected = recent[:recent_quota]
        remaining_slots = max_results - len(selected)
        if remaining_slots > 0:
            selected.extend(older[:remaining_slots])
        remaining_slots = max_results - len(selected)
        if remaining_slots > 0:
            selected.extend(recent[recent_quota:recent_quota + remaining_slots])
        remaining_slots = max_results - len(selected)
        if remaining_slots > 0:
            selected.extend(undated[:remaining_slots])
    else:
        selected = (recent + undated)[:max_results]

    high_count = sum(1 for src in selected if src.get("relevance_tier") == "highly_relevant")
    partial_count = sum(1 for src in selected if src.get("relevance_tier") == "partly_relevant")

    return {
        "query": final_query,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "recent_reference_window": f"{recent_start_year}-{current_year}",
        "databases": searched_databases,
        "skipped_providers": skipped_providers,
        "count": len(selected),
        "requested_count": max_results,
        "provider_errors": provider_errors,
        "excluded_retracted_count": len(excluded_retracted),
        "excluded_retracted_titles": [
            str(r.get("title") or "[untitled]")[:180]
            for r in excluded_retracted[:10]
        ],
        "rejected_irrelevant_count": len(rejected_irrelevant),
        "rejected_irrelevant_titles": [
            str(r.get("title") or "[untitled]")[:180]
            for r in rejected_irrelevant[:12]
        ],
        "relevance_summary": {
            "highly_relevant": high_count,
            "partly_relevant": partial_count,
            "not_attached_as_irrelevant": (
                len(rejected_irrelevant)
                if use_relevance_gate and not attach_not_relevant_sources
                else 0
            ),
        },
        "quality_filters": [
            "retracted/withdrawn/expression-of-concern records excluded",
            "deduplicated by DOI/title",
            "exact-token and compound-concept relevance gate applied",
            "country-only and generic-word matches rejected",
            "requested result count treated as a maximum rather than a quota",
        ],
        "sources": selected,
        "usage_note": (
            "Only highly relevant and partly relevant records are attached by default. "
            "The search may return fewer records than requested rather than fill the list with unrelated papers. "
            "Verify bibliographic details, DOI links, retraction status, and institutional requirements before final submission."
        ),
    }

def _search_openalex(query: str, per_provider: int = 10) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "per-page": min(per_provider, 25),
        "sort": "relevance_score:desc",
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urlencode(params)
    data = _get_json(url)
    results = data.get("results") or []
    records: list[dict[str, Any]] = []
    for item in results:
        title = _clean_text(item.get("display_name"))
        if not title:
            continue
        authorships = item.get("authorships") or []
        authors = []
        for auth in authorships[:6]:
            author = (auth.get("author") or {}).get("display_name")
            if author:
                authors.append(author)
        doi = _normalise_doi(item.get("doi"))
        records.append({
            "title": title,
            "authors": authors,
            "year": item.get("publication_year"),
            "source": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or item.get("host_venue", {}).get("display_name") or "",
            "doi": doi,
            "url": item.get("doi") or item.get("id") or "",
            "abstract": _abstract_from_openalex(item.get("abstract_inverted_index")),
            "type": item.get("type") or "work",
            "database": "OpenAlex",
            "citation_count": item.get("cited_by_count"),
            "is_open_access": (item.get("open_access") or {}).get("is_oa"),
            "is_retracted": bool(item.get("is_retracted", False)),
            "retraction_status": "OpenAlex is_retracted=true" if bool(item.get("is_retracted", False)) else "",
            "apa_hint": _apa_hint(authors, item.get("publication_year"), title, ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "", doi),
        })
    return records


def _search_crossref(query: str, per_provider: int = 10) -> list[dict[str, Any]]:
    params = {
        "query.bibliographic": query,
        "rows": min(per_provider, 25),
    }
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urlencode(params)
    data = _get_json(url)
    items = ((data.get("message") or {}).get("items") or [])
    records: list[dict[str, Any]] = []
    for item in items:
        title = _first(item.get("title"))
        if not title:
            continue
        authors = []
        for auth in item.get("author") or []:
            given = auth.get("given") or ""
            family = auth.get("family") or ""
            full = " ".join([given, family]).strip()
            if full:
                authors.append(full)
        year = _crossref_year(item)
        source = _first(item.get("container-title"))
        doi = _normalise_doi(item.get("DOI"))
        records.append({
            "title": _clean_text(title),
            "authors": authors[:6],
            "year": year,
            "source": _clean_text(source),
            "doi": doi,
            "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
            "abstract": _clean_abstract(item.get("abstract") or ""),
            "type": item.get("type") or "work",
            "database": "Crossref",
            "citation_count": item.get("is-referenced-by-count"),
            "is_open_access": None,
            "is_retracted": _crossref_is_retracted(item),
            "retraction_status": _crossref_retraction_status(item),
            "apa_hint": _apa_hint(authors, year, title, source, doi),
        })
    return records


def _search_semantic_scholar(query: str, per_provider: int = 10) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "limit": min(per_provider, 20),
        "fields": "title,authors,year,venue,url,abstract,citationCount,externalIds,isOpenAccess,publicationTypes",
    }
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(params)
    data = _get_json(url)
    records: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        title = _clean_text(item.get("title"))
        if not title:
            continue
        authors = [a.get("name") for a in item.get("authors") or [] if a.get("name")]
        doi = _normalise_doi((item.get("externalIds") or {}).get("DOI"))
        records.append({
            "title": title,
            "authors": authors[:6],
            "year": item.get("year"),
            "source": _clean_text(item.get("venue")),
            "doi": doi,
            "url": item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
            "abstract": _clean_text(item.get("abstract") or "")[:MAX_ABSTRACT_CHARS],
            "type": ", ".join(item.get("publicationTypes") or []) or "paper",
            "database": "Semantic Scholar",
            "citation_count": item.get("citationCount"),
            "is_open_access": item.get("isOpenAccess"),
            "is_retracted": _looks_retracted({"title": title, "abstract": item.get("abstract") or "", "type": ", ".join(item.get("publicationTypes") or [])}),
            "retraction_status": "title/abstract/type indicates retraction or withdrawal" if _looks_retracted({"title": title, "abstract": item.get("abstract") or "", "type": ", ".join(item.get("publicationTypes") or [])}) else "",
            "apa_hint": _apa_hint(authors, item.get("year"), title, item.get("venue") or "", doi),
        })
    return records


def _search_eric(query: str, per_provider: int = 10) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "format": "json",
        "rows": min(per_provider, 20),
    }
    url = "https://api.ies.ed.gov/eric/?" + urlencode(params)
    data = _get_json(url)
    records: list[dict[str, Any]] = []
    for item in data.get("response", {}).get("docs", []) or []:
        title = _clean_text(item.get("title"))
        if not title:
            continue
        authors = item.get("author") or item.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        year = item.get("publicationdateyear") or item.get("year")
        source = item.get("source") or item.get("publisher") or ""
        url = item.get("url") or item.get("eric_url") or ""
        records.append({
            "title": title,
            "authors": [str(a) for a in authors[:6]],
            "year": year,
            "source": _clean_text(source),
            "doi": "",
            "url": url,
            "abstract": _clean_text(item.get("description") or item.get("abstract") or "")[:MAX_ABSTRACT_CHARS],
            "type": item.get("publicationtype") or "ERIC record",
            "database": "ERIC",
            "citation_count": None,
            "is_open_access": None,
            "is_retracted": _looks_retracted({"title": title, "abstract": item.get("description") or item.get("abstract") or "", "type": item.get("publicationtype") or ""}),
            "retraction_status": "title/abstract/type indicates retraction or withdrawal" if _looks_retracted({"title": title, "abstract": item.get("description") or item.get("abstract") or "", "type": item.get("publicationtype") or ""}) else "",
            "apa_hint": _apa_hint([str(a) for a in authors[:6]], year, title, source, ""),
        })
    return records




def _looks_retracted(record: dict[str, Any]) -> bool:
    haystack = " ".join(str(record.get(k) or "") for k in ["title", "subtitle", "abstract", "type", "source", "retraction_status"])
    return bool(RETRACTION_PATTERN.search(haystack))


def _crossref_retraction_status(item: dict[str, Any]) -> str:
    """Summarise Crossref/Retraction Watch update metadata where present."""
    statuses: list[str] = []
    for key in ["update-to", "updated-by"]:
        value = item.get(key)
        if isinstance(value, list):
            for update in value:
                if str((update or {}).get("type") or "").lower() == "retraction":
                    statuses.append(f"Crossref {key} type=retraction")
        elif isinstance(value, dict):
            for _, updates in value.items():
                if isinstance(updates, list):
                    for update in updates:
                        if str((update or {}).get("type") or "").lower() == "retraction":
                            statuses.append(f"Crossref {key} type=retraction")
    relation = item.get("relation") or {}
    if isinstance(relation, dict):
        for rel_key, rel_values in relation.items():
            if "retract" in str(rel_key).lower():
                statuses.append(f"Crossref relation {rel_key}")
            if isinstance(rel_values, list):
                for rel in rel_values:
                    if "retract" in json.dumps(rel, ensure_ascii=False).lower():
                        statuses.append(f"Crossref relation {rel_key} mentions retraction")
    if _looks_retracted({"title": _first(item.get("title")), "abstract": item.get("abstract") or "", "type": item.get("type") or ""}):
        statuses.append("title/abstract/type indicates retraction or withdrawal")
    return "; ".join(dict.fromkeys(statuses))


def _crossref_is_retracted(item: dict[str, Any]) -> bool:
    return bool(_crossref_retraction_status(item))


def _is_retracted_record(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    value = record.get("is_retracted")
    if isinstance(value, bool) and value:
        return True
    if str(value).strip().lower() in {"true", "yes", "1", "retracted", "withdrawn"}:
        return True
    return _looks_retracted(record)

def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={
        "User-Agent": "ProjectReadyAI/0.1 (scholarly metadata search; mailto optional)",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:  # nosec B310 - public metadata APIs only
        raw = response.read().decode("utf-8", errors="replace")
    time.sleep(0.12)  # be gentle to public APIs
    return json.loads(raw)


def _query_is_education_related(query: str) -> bool:
    return bool(set(_tokenise(query)) & _EDUCATION_TERMS)


def _query_concepts(query: str) -> tuple[list[str], list[str]]:
    tokens = _tokenise(query)
    context_vocabulary = _GEOGRAPHIC_TERMS | _POPULATION_CONTEXT_TERMS
    context_terms = [token for token in tokens if token in context_vocabulary]
    core_terms: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in _SEARCH_STOPWORDS or token in _GENERIC_RESEARCH_TERMS or token in context_vocabulary:
            continue
        if token not in seen:
            seen.add(token)
            core_terms.append(token)
    return core_terms[:12], list(dict.fromkeys(context_terms))[:6]


def _record_tokens(record: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    title_tokens = set(_tokenise(record.get("title") or ""))
    abstract_tokens = set(_tokenise(record.get("abstract") or ""))
    source_tokens = set(_tokenise(record.get("source") or ""))
    return title_tokens, abstract_tokens, source_tokens


def _build_relevance_profile(query: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    core_terms, context_terms = _query_concepts(query)
    frequencies: Counter[str] = Counter()
    for record in records:
        title_tokens, abstract_tokens, _ = _record_tokens(record)
        combined = title_tokens | abstract_tokens
        for term in core_terms:
            if term in combined:
                frequencies[term] += 1

    present_terms = [term for term in core_terms if frequencies.get(term, 0) > 0]
    anchor_pool = present_terms or core_terms
    if len(core_terms) <= 3:
        # Short queries usually describe one compound concept. Require the
        # rarest term, such as "passthrough", so broad "exchange rate" papers
        # do not pass the gate.
        anchors = sorted(
            anchor_pool,
            key=lambda term: (frequencies.get(term, 10**6), -len(term), term),
        )[:1]
    else:
        # Longer queries often contain several constructs. Any substantive
        # construct may justify partial relevance, so retain all concept terms
        # as possible anchors and rely on coverage thresholds for the tier.
        anchors = list(anchor_pool)
    return {
        "core_terms": core_terms,
        "context_terms": context_terms,
        "anchors": anchors,
    }


def _classify_relevance(record: dict[str, Any], relevance_profile: dict[str, Any]) -> tuple[str, str, str, dict[str, float]]:
    core_terms: list[str] = relevance_profile.get("core_terms") or []
    context_terms: list[str] = relevance_profile.get("context_terms") or []
    anchors: list[str] = relevance_profile.get("anchors") or []

    title_tokens, abstract_tokens, source_tokens = _record_tokens(record)
    full_tokens = title_tokens | abstract_tokens | source_tokens
    core_set = set(core_terms)
    title_hits = core_set & title_tokens
    full_hits = core_set & full_tokens
    anchor_title_hits = set(anchors) & title_tokens
    anchor_full_hits = set(anchors) & full_tokens
    context_hits = set(context_terms) & full_tokens

    core_count = max(1, len(core_set))
    title_coverage = len(title_hits) / core_count
    full_coverage = len(full_hits) / core_count
    context_coverage = len(context_hits) / max(1, len(context_terms)) if context_terms else 0.0

    if not core_terms:
        # A defensive fallback for exceptionally short or generic queries.
        tier = "partly_relevant" if context_hits else "not_relevant"
    elif len(core_terms) <= 2:
        if full_coverage == 1.0 and len(title_hits) >= 1 and anchor_full_hits:
            tier = "highly_relevant"
        elif full_coverage == 1.0 and anchor_full_hits:
            tier = "partly_relevant"
        else:
            tier = "not_relevant"
    else:
        if len(core_terms) >= 4:
            # Multi-construct studies need literature on the full model and on
            # individual constructs. Two substantive concept matches can be a
            # defensible partly relevant source even when the paper does not
            # cover every variable in the thesis title.
            if anchor_full_hits and title_coverage >= 0.40 and full_coverage >= 0.65:
                tier = "highly_relevant"
            elif anchor_full_hits and title_coverage >= 0.25 and full_coverage >= 0.40:
                tier = "partly_relevant"
            else:
                tier = "not_relevant"
        elif anchor_full_hits and title_coverage >= 0.50 and full_coverage >= 0.75:
            tier = "highly_relevant"
        elif anchor_full_hits and (
            (title_coverage >= 0.34 and full_coverage >= 0.50)
            or title_coverage >= 0.50
        ):
            tier = "partly_relevant"
        else:
            tier = "not_relevant"

    matched = ", ".join(sorted(full_hits)) or "none"
    anchor_text = ", ".join(sorted(anchor_full_hits)) or "none"
    if tier == "highly_relevant":
        reason = (
            f"Strong concept match: {len(full_hits)}/{len(core_terms)} core terms matched "
            f"({matched}); distinctive anchor match: {anchor_text}."
        )
        suggested_use = "Suitable for direct use in the study background, literature review, theory, methods or discussion where the claim aligns."
    elif tier == "partly_relevant":
        reason = (
            f"Partial but defensible concept match: {len(full_hits)}/{len(core_terms)} core terms matched "
            f"({matched}); distinctive anchor match: {anchor_text}."
        )
        suggested_use = "Use only for the specific construct, mechanism, method or comparative context it directly addresses."
    else:
        reason = (
            f"Rejected by relevance gate: only {len(full_hits)}/{len(core_terms)} core terms matched "
            f"({matched}), or no distinctive topic anchor was present."
        )
        suggested_use = "Do not attach or cite for this search unless the user independently confirms a direct connection."

    return tier, reason, suggested_use, {
        "title_coverage": round(title_coverage, 4),
        "full_coverage": round(full_coverage, 4),
        "context_coverage": round(context_coverage, 4),
        "anchor_hit": 1.0 if anchor_full_hits else 0.0,
    }


def _dedupe_and_rank(records: list[dict[str, Any]], query: str, recent_start_year: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        title = _clean_text(record.get("title"))
        doi = _normalise_doi(record.get("doi"))
        key = doi or re.sub(r"[^a-z0-9]+", "", title.lower())[:100]
        if not title or key in seen:
            continue
        if _is_retracted_record(record):
            continue
        seen.add(key)
        item = dict(record)
        item["title"] = title
        item["doi"] = doi
        item["abstract"] = _clean_text(item.get("abstract") or "")[:MAX_ABSTRACT_CHARS]
        deduped.append(item)

    relevance_profile = _build_relevance_profile(query, deduped)
    for record in deduped:
        tier, reason, suggested_use, metrics = _classify_relevance(record, relevance_profile)
        record["relevance_tier"] = tier
        record["relevance_reason"] = reason
        record["suggested_use"] = suggested_use
        record["relevance_metrics"] = metrics
        record["search_query"] = query
        record["attachment_origin"] = "automated_source_search"
        record["relevance_score"] = _relevance_score(
            record,
            query,
            recent_start_year,
            relevance_profile=relevance_profile,
        )

    deduped.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    return deduped


def _relevance_score(
    record: dict[str, Any],
    query: str,
    recent_start_year: int,
    relevance_profile: dict[str, Any] | None = None,
) -> float:
    if _is_retracted_record(record):
        return -9999.0

    profile = relevance_profile or _build_relevance_profile(query, [record])
    metrics = record.get("relevance_metrics") or _classify_relevance(record, profile)[3]
    tier = str(record.get("relevance_tier") or "not_relevant")
    tier_bonus = {
        "highly_relevant": 100.0,
        "partly_relevant": 55.0,
        "not_relevant": -80.0,
    }.get(tier, -80.0)

    year = _safe_int(record.get("year")) or 0
    recency = 12 if year >= recent_start_year else max(0, 6 - max(0, recent_start_year - year) * 0.4)
    doi_bonus = 4 if record.get("doi") else 0
    abstract_bonus = 3 if record.get("abstract") else 0
    citations = _safe_int(record.get("citation_count")) or 0
    citation_bonus = min(6, citations ** 0.5) if citations else 0
    db_bonus = {"OpenAlex": 2, "Crossref": 2, "Semantic Scholar": 2, "ERIC": 1}.get(record.get("database"), 0)

    lexical = (
        float(metrics.get("title_coverage", 0)) * 34
        + float(metrics.get("full_coverage", 0)) * 20
        + float(metrics.get("context_coverage", 0)) * 5
        + float(metrics.get("anchor_hit", 0)) * 10
    )
    return float(tier_bonus + lexical + recency + doi_bonus + abstract_bonus + citation_bonus + db_bonus)

def _abstract_from_openalex(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, indexes in index.items():
        for idx in indexes:
            positions[int(idx)] = word
    words = [positions[i] for i in sorted(positions)]
    return _clean_text(" ".join(words))[:MAX_ABSTRACT_CHARS]


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0] or "")
    return str(value or "")


def _crossref_year(item: dict[str, Any]) -> int | None:
    for key in ["issued", "published-print", "published-online"]:
        parts = ((item.get(key) or {}).get("date-parts") or [])
        if parts and parts[0]:
            return _safe_int(parts[0][0])
    return None


def _clean_abstract(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return _clean_text(value)[:MAX_ABSTRACT_CHARS]


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalise_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def _safe_int(value: Any) -> int | None:
    """Return a safe integer year/count from messy provider metadata.

    Open scholarly APIs sometimes return None, empty strings, floats, date strings,
    year ranges, or values such as "2021-01-01". This helper prevents comparison
    errors during ranking and recent/older filtering.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == value else None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\d{4,}", text)
    if match:
        try:
            return int(match.group(0))
        except Exception:
            return None
    try:
        return int(text)
    except Exception:
        return None


def _apa_hint(authors: list[str], year: Any, title: str, source: str, doi: str) -> str:
    author_text = _format_authors_for_hint(authors)
    year_text = str(year or "n.d.")
    source_text = f" {source}." if source else ""
    doi_text = f" https://doi.org/{doi}" if doi else ""
    return _clean_text(f"{author_text} ({year_text}). {title}.{source_text}{doi_text}")


def _format_authors_for_hint(authors: list[str]) -> str:
    if not authors:
        return "[Author]"
    cleaned = [_clean_text(a) for a in authors if _clean_text(a)]
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} & {cleaned[1]}"
    return f"{cleaned[0]} et al."
