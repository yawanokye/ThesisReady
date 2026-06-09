from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 12
MAX_QUERY_CHARS = 220
MAX_ABSTRACT_CHARS = 650


def build_source_query(profile: dict[str, Any], user_query: str = "") -> str:
    """Create a focused literature-search query from the project profile and optional user terms."""
    pieces: list[str] = []
    if user_query.strip():
        pieces.append(user_query.strip())

    for key in ["title", "research_area"]:
        value = str(profile.get(key) or "").strip()
        if value:
            pieces.append(value)

    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [x.strip() for x in re.split(r"\n|;", objectives) if x.strip()]
    pieces.extend(str(obj).strip() for obj in objectives[:3] if str(obj).strip())

    context = str(profile.get("study_context") or "").strip()
    if context:
        # Add only the first sentence or first 160 characters to avoid weak, overlong searches.
        first_sentence = re.split(r"(?<=[.!?])\s+", context)[0]
        pieces.append(first_sentence[:160])

    query = " ".join(pieces)
    query = re.sub(r"\s+", " ", query).strip()
    return query[:MAX_QUERY_CHARS]


def search_literature_sources(
    profile: dict[str, Any],
    query: str = "",
    max_results: int = 12,
    include_older_foundational: bool = True,
) -> dict[str, Any]:
    """Search open scholarly metadata providers and return deduplicated source records.

    The function deliberately retrieves metadata only. It does not download copyrighted papers,
    and it does not generate references that are absent from returned metadata.
    """
    final_query = build_source_query(profile, query)
    if not final_query:
        raise ValueError("Please provide a project title, research area, objective, or search terms before finding sources.")

    max_results = max(3, min(int(max_results or 12), 30))
    current_year = datetime.now().year
    recent_start_year = current_year - 5

    providers = [
        _search_openalex,
        _search_crossref,
        _search_semantic_scholar,
        _search_eric,
    ]

    records: list[dict[str, Any]] = []
    provider_errors: list[dict[str, str]] = []
    for provider in providers:
        try:
            records.extend(provider(final_query, per_provider=max(5, max_results)))
        except Exception as exc:
            provider_errors.append({"provider": provider.__name__.replace("_search_", ""), "error": str(exc)[:220]})

    deduped = _dedupe_and_rank(records, query=final_query, recent_start_year=recent_start_year)

    for src in deduped:
        src.update(_classify_source_relevance(profile, final_query, src))

    deduped.sort(
        key=lambda item: (
            _relevance_tier_rank(item.get("relevance_tier")),
            item.get("relevance_score", 0),
        ),
        reverse=True,
    )

    # Prefer recent sources but keep strong older/foundational sources where needed.
    # Some metadata providers return None, empty strings, ranges, or non-numeric years.
    # Normalise years before comparison so the source search never fails on undated records.
    recent: list[dict[str, Any]] = []
    older: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []
    for src in deduped:
        year = _safe_int(src.get("year"))
        if year is None:
            undated.append(src)
        elif year >= recent_start_year:
            recent.append(src)
        else:
            older.append(src)

    if include_older_foundational:
        selected = recent[: max_results]
        remaining_slots = max_results - len(selected)
        if remaining_slots > 0:
            selected.extend(older[:remaining_slots])
        remaining_slots = max_results - len(selected)
        if remaining_slots > 0:
            selected.extend(undated[:remaining_slots])
    else:
        selected = (recent + undated)[:max_results]

    return {
        "query": final_query,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "recent_reference_window": f"{recent_start_year}-{current_year}",
        "databases": ["OpenAlex", "Crossref", "Semantic Scholar", "ERIC"],
        "count": len(selected),
        "provider_errors": provider_errors,
        "relevance_counts": _relevance_counts(selected),
        "sources": selected,
        "usage_note": (
            "Use these retrieved records as an additional evidence bank. Prioritise records marked highly_relevant and partly_relevant, "
            "but cite a source only where it directly supports the claim, variable, method, theory, context, finding, or gap being discussed. "
            "Do not cite sources marked not_relevant. Verify bibliographic details, DOI links, and institutional requirements before final submission. "
            "If the results do not match the topic well, refine the search terms and run the search again."
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
            "apa_hint": _apa_hint(authors, item.get("publication_year"), title, ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "", doi),
        })
    return records


def _search_crossref(query: str, per_provider: int = 10) -> list[dict[str, Any]]:
    params = {
        "query.bibliographic": query,
        "rows": min(per_provider, 25),
        "select": "title,author,issued,container-title,DOI,URL,type,is-referenced-by-count,abstract,published-print,published-online",
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
            "apa_hint": _apa_hint([str(a) for a in authors[:6]], year, title, source, ""),
        })
    return records



RELEVANCE_STOPWORDS = {
    "about", "after", "among", "based", "because", "between", "chapter", "could", "from", "project", "research",
    "role", "selected", "study", "their", "these", "this", "with", "within", "work", "works", "effect", "effects",
    "relationship", "relationships", "mediating", "mediator", "students", "student", "undergraduate", "institution", "institutions",
}

DOMAIN_SIGNAL_TERMS = {
    "regret", "dissatisfaction", "dissatisfied", "satisfaction", "expectation", "expectations", "choice", "decision",
    "post-choice", "postchoice", "undergraduate", "student", "students", "university", "higher education", "private higher education",
    "institutional choice", "ghana", "ghanaian", "tertiary", "enrolment", "enrollment", "service quality", "disconfirmation",
}

LOW_VALUE_RECORD_PATTERNS = [
    r"^review for\b",
    r"^decision letter for\b",
    r"^author response for\b",
    r"^peer review",
    r"\bpreprint review\b",
]

OFF_TOPIC_PATTERNS = [
    r"\bbody dissatisfaction\b",
    r"\binstagram\b",
    r"\balcohol-related regret\b",
    r"\bwage dissatisfaction\b",
    r"\bunion expectations\b",
]


def _relevance_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"highly_relevant": 0, "partly_relevant": 0, "not_relevant": 0}
    for src in sources:
        tier = str(src.get("relevance_tier") or "not_relevant")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _relevance_tier_rank(tier: Any) -> int:
    return {"highly_relevant": 3, "partly_relevant": 2, "not_relevant": 1}.get(str(tier or ""), 0)


def _classify_source_relevance(profile: dict[str, Any], query: str, record: dict[str, Any]) -> dict[str, str]:
    """Classify a retrieved record before it reaches the drafting engine.

    This is a conservative relevance gate. It prevents keyword-only matches, review
    records, decision letters, or unrelated studies from being treated as citable
    evidence simply because they appeared in a search result.
    """
    title = _clean_text(record.get("title") or "")
    abstract = _clean_text(record.get("abstract") or "")
    source = _clean_text(record.get("source") or "")
    record_type = _clean_text(record.get("type") or "")
    haystack = f"{title} {abstract} {source} {record_type}".lower()
    title_lower = title.lower()

    if any(re.search(pattern, title_lower) for pattern in LOW_VALUE_RECORD_PATTERNS):
        return {
            "relevance_tier": "not_relevant",
            "relevance_reason": "This is a review, decision letter, author response, or other non-substantive metadata record rather than a citable empirical or theoretical source.",
            "suggested_use": "Do not cite in the chapter. Use a placeholder or rerun the search with more focused terms.",
        }

    if any(re.search(pattern, haystack) for pattern in OFF_TOPIC_PATTERNS):
        return {
            "relevance_tier": "not_relevant",
            "relevance_reason": "The record uses similar words but addresses a different topic or population, so it is not suitable evidence for this study.",
            "suggested_use": "Do not cite unless a human reviewer confirms a specific theoretical or methodological reason for using it.",
        }

    query_terms = _meaningful_terms(query)
    profile_terms = _profile_terms(profile)
    combined_terms = sorted(query_terms | profile_terms)
    title_hits = [term for term in combined_terms if term in title_lower]
    body_hits = [term for term in combined_terms if term in haystack]
    signal_hits = [term for term in DOMAIN_SIGNAL_TERMS if term in haystack]

    has_regret = "regret" in haystack or "post-choice" in haystack or "postchoice" in haystack
    has_dissatisfaction = "dissatisfaction" in haystack or "dissatisfied" in haystack or "satisfaction" in haystack
    has_expectation = "expectation" in haystack or "expectations" in haystack or "disconfirmation" in haystack
    has_higher_ed = any(term in haystack for term in ["higher education", "university", "tertiary", "college", "post-secondary", "undergraduate", "foundation year"])
    has_student_context = any(term in haystack for term in ["student", "students", "undergraduate", "medical students", "healthcare students"])
    has_ghana = "ghana" in haystack or "ghanaian" in haystack
    has_private_he = "private higher education" in haystack or ("private" in haystack and has_higher_ed)

    if has_student_context and has_regret and not has_higher_ed:
        return {
            "relevance_tier": "partly_relevant",
            "relevance_reason": "Addresses regret among students, but not within private higher education or the full study context.",
            "suggested_use": "Use cautiously for conceptual support on student regret only, not as direct evidence on Ghanaian private higher education.",
        }

    if has_higher_ed and ((has_regret and has_dissatisfaction) or (has_regret and has_expectation)):
        return {
            "relevance_tier": "highly_relevant",
            "relevance_reason": "Directly addresses the study constructs within a higher education or student-choice context.",
            "suggested_use": "Consider for conceptual review, empirical review, or discussion where the claim concerns regret, dissatisfaction, expectations, or mediation.",
        }

    if (has_regret and has_dissatisfaction) or (has_regret and has_expectation):
        return {
            "relevance_tier": "partly_relevant",
            "relevance_reason": "Addresses regret with dissatisfaction or expectations, but outside the exact higher education context.",
            "suggested_use": "Use only for conceptual support where the argument concerns regret, dissatisfaction, or expectation mechanisms, not for Ghanaian higher education context.",
        }

    if has_higher_ed and (has_regret or has_dissatisfaction or has_expectation):
        return {
            "relevance_tier": "highly_relevant",
            "relevance_reason": "Directly connects higher education or students with regret, dissatisfaction, expectations, or student experience.",
            "suggested_use": "Consider for Chapter One context, Chapter Two conceptual/empirical review, or Chapter Four discussion.",
        }

    if has_ghana and has_higher_ed:
        return {
            "relevance_tier": "highly_relevant",
            "relevance_reason": "Highly relevant to Ghanaian higher education context, even if it does not measure the full model.",
            "suggested_use": "Use for Ghana-specific background, private higher education context, student choice, or problem framing where appropriate.",
        }

    if has_private_he or (has_higher_ed and len(signal_hits) >= 2) or len(title_hits) >= 3:
        return {
            "relevance_tier": "partly_relevant",
            "relevance_reason": "Partly relevant to higher education choice, student experience, service evaluation, or one construct in the study.",
            "suggested_use": "Use only where it supports a specific claim. Do not cite it as evidence for the entire regret-expectation-dissatisfaction model.",
        }

    if len(body_hits) >= 5 and len(signal_hits) >= 1:
        return {
            "relevance_tier": "partly_relevant",
            "relevance_reason": "Contains several topic terms and at least one construct signal, but the fit appears indirect.",
            "suggested_use": "Use cautiously if the paragraph concerns the specific construct, method, or context reflected in the source.",
        }

    return {
        "relevance_tier": "not_relevant",
        "relevance_reason": "The record does not clearly support the study topic, constructs, context, theory, method, empirical gap, or discussion.",
        "suggested_use": "Do not cite. Keep it out of the reference list unless a human reviewer confirms relevance.",
    }


def _meaningful_terms(text: str) -> set[str]:
    terms = set()
    lower = (text or "").lower()
    for phrase in ["post-choice", "post choice", "higher education", "private higher education", "student expectations", "student dissatisfaction", "career choice regret", "student choice", "university choice"]:
        if phrase in lower:
            terms.add(phrase)
    for term in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", lower):
        cleaned = term.strip("-")
        if cleaned and cleaned not in RELEVANCE_STOPWORDS:
            terms.add(cleaned)
    return terms


def _profile_terms(profile: dict[str, Any]) -> set[str]:
    pieces: list[str] = []
    for key in ["title", "research_area", "study_context", "citation_evidence_notes"]:
        value = str(profile.get(key) or "").strip()
        if value:
            pieces.append(value)
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        pieces.append(objectives)
    elif isinstance(objectives, list):
        pieces.extend(str(x) for x in objectives if str(x).strip())
    return _meaningful_terms(" ".join(pieces))

def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={
        "User-Agent": "ProjectReadyAI/0.1 (scholarly metadata search; mailto optional)",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:  # nosec B310 - public metadata APIs only
        raw = response.read().decode("utf-8", errors="replace")
    time.sleep(0.12)  # be gentle to public APIs
    return json.loads(raw)


def _dedupe_and_rank(records: list[dict[str, Any]], query: str, recent_start_year: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        title = _clean_text(record.get("title"))
        doi = _normalise_doi(record.get("doi"))
        key = doi or re.sub(r"[^a-z0-9]+", "", title.lower())[:100]
        if not title or key in seen:
            continue
        seen.add(key)
        record["title"] = title
        record["doi"] = doi
        record["abstract"] = _clean_text(record.get("abstract") or "")[:MAX_ABSTRACT_CHARS]
        record["relevance_score"] = _relevance_score(record, query, recent_start_year)
        deduped.append(record)
    deduped.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    return deduped


def _relevance_score(record: dict[str, Any], query: str, recent_start_year: int) -> float:
    query_terms = {term for term in re.findall(r"[a-zA-Z]{4,}", query.lower()) if len(term) > 3}
    haystack = " ".join([str(record.get("title") or ""), str(record.get("abstract") or ""), str(record.get("source") or "")]).lower()
    term_hits = sum(1 for term in query_terms if term in haystack)
    year = _safe_int(record.get("year")) or 0
    recency = 12 if year >= recent_start_year else max(0, 6 - max(0, recent_start_year - year) * 0.4)
    doi_bonus = 6 if record.get("doi") else 0
    abstract_bonus = 3 if record.get("abstract") else 0
    citations = _safe_int(record.get("citation_count")) or 0
    citation_bonus = min(8, citations ** 0.5) if citations else 0
    db_bonus = {"OpenAlex": 2, "Crossref": 2, "Semantic Scholar": 2, "ERIC": 1}.get(record.get("database"), 0)
    return float(term_hits * 4 + recency + doi_bonus + abstract_bonus + citation_bonus + db_bonus)


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
