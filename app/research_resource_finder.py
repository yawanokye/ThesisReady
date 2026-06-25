from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.source_finder import search_literature_sources

RESOURCE_TIMEOUT_SECONDS = max(4, int(os.getenv("TOPIC_RESOURCE_SEARCH_TIMEOUT_SECONDS", "10") or 10))
MAX_DATASET_RESULTS = max(3, min(int(os.getenv("TOPIC_DATASET_RESULTS", "8") or 8), 15))
MAX_INSTRUMENT_RESULTS = max(3, min(int(os.getenv("TOPIC_INSTRUMENT_RESULTS", "8") or 8), 15))

_INSTRUMENT_TERMS = re.compile(
    r"\b(scale|questionnaire|instrument|inventory|measure|measurement|psychometric|validation|validated|"
    r"reliability|validity|index|survey tool|interview guide|interview protocol|topic guide|observation checklist|"
    r"assessment tool|screening tool|protocol|checklist)\b",
    flags=re.IGNORECASE,
)

_SECONDARY_METHOD_TERMS = {
    "secondary data",
    "econometrics",
    "time-series econometrics",
    "panel data econometrics",
}

# This catalogue is searched locally by construct/topic keywords. Live dataset records from
# DataCite and Harvard Dataverse are added separately. Keeping the catalogue local avoids
# presenting invented named datasets when a live search is temporarily unavailable.
OFFICIAL_DATA_PORTALS: list[dict[str, Any]] = [
    {
        "name": "World Development Indicators",
        "provider": "World Bank",
        "url": "https://databank.worldbank.org/source/world-development-indicators",
        "description": "Cross-country development indicators covering economic, social, environmental and institutional topics.",
        "tags": ["gdp", "inflation", "exchange rate", "trade", "education", "health", "poverty", "population", "environment", "finance", "development"],
        "access_note": "Check indicator definitions, country coverage, frequency and revision history before analysis.",
    },
    {
        "name": "IMF Data",
        "provider": "International Monetary Fund",
        "url": "https://data.imf.org/",
        "description": "Macroeconomic, fiscal, monetary, balance-of-payments and financial-sector series.",
        "tags": ["inflation", "exchange rate", "interest rate", "fiscal", "debt", "money", "banking", "financial", "balance of payments", "macroeconomic"],
        "access_note": "Confirm database, series code, units, frequency and country comparability.",
    },
    {
        "name": "ILOSTAT Data Explorer",
        "provider": "International Labour Organization",
        "url": "https://rshiny.ilo.org/dataexplorer/",
        "description": "Labour-market indicators including employment, unemployment, earnings, informality and working conditions.",
        "tags": ["employment", "unemployment", "labour", "labor", "wage", "earnings", "informal", "productivity", "work", "occupation"],
        "access_note": "Review indicator concepts, age groups, sex disaggregation and estimation method.",
    },
    {
        "name": "Global Health Observatory",
        "provider": "World Health Organization",
        "url": "https://www.who.int/data/gho",
        "description": "International public-health indicators, disease burden, service coverage and health-system data.",
        "tags": ["health", "mortality", "disease", "hospital", "healthcare", "nutrition", "maternal", "child", "mental health", "service coverage"],
        "access_note": "Check the indicator metadata, estimation method and whether values are observed or modelled.",
    },
    {
        "name": "UNESCO Institute for Statistics",
        "provider": "UNESCO",
        "url": "https://uis.unesco.org/",
        "description": "Comparable education, science, culture and communication statistics.",
        "tags": ["education", "school", "student", "teacher", "literacy", "enrolment", "enrollment", "research", "science", "higher education"],
        "access_note": "Verify education level definitions, academic year and missing-data treatment.",
    },
    {
        "name": "FAOSTAT",
        "provider": "Food and Agriculture Organization",
        "url": "https://www.fao.org/faostat/",
        "description": "Agriculture, food, land use, prices, production, trade and food-security statistics.",
        "tags": ["agriculture", "food", "crop", "livestock", "farm", "land", "food security", "agricultural trade", "production", "commodity"],
        "access_note": "Check commodity classifications, measurement units and reporting gaps.",
    },
    {
        "name": "UN Comtrade",
        "provider": "United Nations",
        "url": "https://comtradeplus.un.org/",
        "description": "International merchandise-trade records by reporter, partner, product and period.",
        "tags": ["trade", "export", "import", "commodity", "tariff", "product", "bilateral trade", "market"],
        "access_note": "Define the trade classification, reporter/partner direction, valuation and aggregation level.",
    },
    {
        "name": "Demographic and Health Surveys",
        "provider": "The DHS Program",
        "url": "https://dhsprogram.com/data/",
        "description": "Household and individual survey microdata on population, health, nutrition and related social outcomes.",
        "tags": ["household", "demographic", "fertility", "maternal", "child", "nutrition", "health", "women", "population", "survey"],
        "access_note": "Registration and project approval may be required. Respect sample weights, complex survey design and restricted variables.",
    },
    {
        "name": "Afrobarometer Data",
        "provider": "Afrobarometer",
        "url": "https://www.afrobarometer.org/data/",
        "description": "Public-opinion survey data on governance, democracy, public services, institutions and social conditions in Africa.",
        "tags": ["governance", "democracy", "trust", "corruption", "public service", "citizen", "political", "institution", "africa", "attitude"],
        "access_note": "Review round, questionnaire wording, country sample and survey weights before pooling data.",
    },
    {
        "name": "Enterprise Surveys",
        "provider": "World Bank",
        "url": "https://www.enterprisesurveys.org/",
        "description": "Firm-level survey data on the business environment, finance, performance, innovation, regulation and infrastructure.",
        "tags": ["firm", "business", "enterprise", "finance", "innovation", "productivity", "performance", "regulation", "infrastructure", "private sector"],
        "access_note": "Check survey year, sampling frame, country questionnaire and variable harmonisation.",
    },
    {
        "name": "IPUMS",
        "provider": "IPUMS",
        "url": "https://www.ipums.org/",
        "description": "Harmonised census and survey microdata for population, labour, health and related social research.",
        "tags": ["census", "population", "household", "labour", "labor", "migration", "employment", "demographic", "microdata", "survey"],
        "access_note": "Registration and data-use conditions apply. Use harmonised codes and appropriate weights.",
    },
    {
        "name": "Ghana Statistical Service Data",
        "provider": "Ghana Statistical Service",
        "url": "https://statsghana.gov.gh/",
        "description": "Official Ghanaian census, household, labour, price, demographic and economic statistics.",
        "tags": ["ghana", "census", "household", "population", "labour", "labor", "inflation", "poverty", "employment", "regional"],
        "access_note": "Confirm the survey edition, geographic level, codebook and access conditions for microdata.",
    },
    {
        "name": "Bank of Ghana Economic Data",
        "provider": "Bank of Ghana",
        "url": "https://www.bog.gov.gh/economic-data/",
        "description": "Ghanaian monetary, banking, interest-rate, exchange-rate and macro-financial series.",
        "tags": ["ghana", "banking", "interest rate", "exchange rate", "inflation", "money", "credit", "financial", "monetary", "bank"],
        "access_note": "Check series frequency, definitions, rebasing and publication revisions.",
    },
    {
        "name": "OECD Data Explorer",
        "provider": "OECD",
        "url": "https://data-explorer.oecd.org/",
        "description": "Comparable economic, education, labour, governance, social and environmental indicators for OECD and partner economies.",
        "tags": ["oecd", "economy", "education", "labour", "labor", "governance", "tax", "environment", "social", "productivity"],
        "access_note": "Check country membership, indicator definition, frequency and comparability over time.",
    },
]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokenise(value: Any) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "into", "among", "between", "within", "study", "effect", "effects",
        "impact", "influence", "relationship", "analysis", "selected", "possible", "principal", "factors", "outcomes",
    }
    return {
        token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", _clean(value).lower())
        if token not in stop
    }


def _constructs_for_idea(idea: dict[str, Any]) -> list[str]:
    values = idea.get("possible_variables_or_constructs") or []
    if not isinstance(values, list):
        values = [values]
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned[:8]


def _global_construct_pool(payload: dict[str, Any], ideas: list[dict[str, Any]]) -> list[str]:
    phrases: list[str] = []
    for idea in ideas:
        phrases.extend(_constructs_for_idea(idea))
    phrases.extend([
        _clean(payload.get("research_area")),
        _clean(payload.get("context")),
        _clean(payload.get("country_region")),
    ])
    counter = Counter(p.lower() for p in phrases if p)
    unique: list[str] = []
    for phrase, _ in counter.most_common():
        original = next((p for p in phrases if p.lower() == phrase), phrase)
        if original and original not in unique:
            unique.append(original)
    return unique[:10]


def research_resource_modes(payload: dict[str, Any]) -> dict[str, bool]:
    methodology = _clean(payload.get("methodology")).lower()
    data_type = _clean(payload.get("data_type")).lower()

    systematic = "systematic literature review" in methodology
    secondary = (
        methodology in _SECONDARY_METHOD_TERMS
        or any(term in methodology for term in ["secondary", "econometric", "time-series", "panel data"])
        or "secondary data available" in data_type
        or "both primary and secondary" in data_type
        or data_type == "not sure"
    )
    instrument = (
        systematic
        or any(term in methodology for term in ["survey", "qualitative", "mixed", "case study"])
        or "primary data available" in data_type
        or "both primary and secondary" in data_type
        or data_type == "not sure"
    )
    if methodology in _SECONDARY_METHOD_TERMS and "both" not in data_type:
        instrument = False
    return {"secondary": secondary, "instrument": instrument, "systematic": systematic}


def _get_json(url: str, accept: str = "application/json") -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "ProjectReadyAI/0.2 (research resource discovery)",
            "Accept": accept,
        },
    )
    with urlopen(request, timeout=RESOURCE_TIMEOUT_SECONDS) as response:  # nosec B310 - public metadata APIs only
        raw = response.read().decode("utf-8", errors="replace")
    time.sleep(0.08)
    return json.loads(raw)


def _dataset_query(payload: dict[str, Any], constructs: list[str]) -> str:
    pieces = [
        _clean(payload.get("research_area")),
        *constructs[:4],
        _clean(payload.get("country_region")),
        _clean(payload.get("context")),
    ]
    query = " ".join(x for x in pieces if x)
    return re.sub(r"\s+", " ", query).strip()[:220]


def _search_datacite_datasets(query: str, limit: int = MAX_DATASET_RESULTS) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "resource-type-id": "dataset",
        "page[size]": min(max(3, limit), 15),
    }
    url = "https://api.datacite.org/dois?" + urlencode(params)
    payload = _get_json(url, accept="application/vnd.api+json")
    results: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        attributes = item.get("attributes") or {}
        titles = attributes.get("titles") or []
        title = _clean((titles[0] or {}).get("title") if titles else "")
        if not title:
            continue
        creators = []
        for creator in (attributes.get("creators") or [])[:6]:
            name = _clean(creator.get("name") or " ".join(filter(None, [creator.get("givenName"), creator.get("familyName")])))
            if name:
                creators.append(name)
        descriptions = attributes.get("descriptions") or []
        description = _clean((descriptions[0] or {}).get("description") if descriptions else "")
        subjects = [_clean(x.get("subject")) for x in (attributes.get("subjects") or []) if _clean(x.get("subject"))]
        doi = _clean(attributes.get("doi") or item.get("id"))
        landing = _clean(attributes.get("url")) or (f"https://doi.org/{doi}" if doi else "")
        results.append({
            "name": title,
            "provider": _clean(attributes.get("publisher")) or "DataCite repository",
            "description": description[:650],
            "authors_or_creators": creators,
            "year": attributes.get("publicationYear") or "",
            "doi": doi,
            "url": landing,
            "subjects": subjects[:8],
            "source_type": "Live dataset record",
            "discovery_database": "DataCite",
            "access_note": "Open the repository record to inspect files, licence, geographic coverage, variables, codebook and access restrictions.",
        })
    return results


def _search_harvard_dataverse(query: str, limit: int = MAX_DATASET_RESULTS) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "type": "dataset",
        "per_page": min(max(3, limit), 15),
        "fq": "publicationStatus:Published",
    }
    url = "https://dataverse.harvard.edu/api/search?" + urlencode(params)
    payload = _get_json(url)
    results: list[dict[str, Any]] = []
    for item in ((payload.get("data") or {}).get("items") or []):
        title = _clean(item.get("name") or item.get("title"))
        if not title:
            continue
        authors = item.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        results.append({
            "name": title,
            "provider": _clean(item.get("publisher") or item.get("name_of_dataverse")) or "Harvard Dataverse",
            "description": _clean(item.get("description"))[:650],
            "authors_or_creators": [_clean(x) for x in authors[:6] if _clean(x)],
            "year": _clean(item.get("published_at"))[:4],
            "doi": _clean(item.get("global_id")),
            "url": _clean(item.get("url")),
            "subjects": [_clean(x) for x in (item.get("subjects") or []) if _clean(x)][:8],
            "source_type": "Live dataset record",
            "discovery_database": "Harvard Dataverse",
            "access_note": "Open the dataset page to confirm files, version, licence, variable documentation and whether restricted access applies.",
        })
    return results


def _dedupe_dataset_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = _clean(record.get("doi") or record.get("url") or record.get("name")).lower()
        key = re.sub(r"[^a-z0-9]+", "", key)[:180]
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def _matched_constructs(record: dict[str, Any], constructs: list[str]) -> list[str]:
    haystack = " ".join([
        _clean(record.get("name") or record.get("title")),
        _clean(record.get("description") or record.get("abstract")),
        " ".join(record.get("subjects") or []),
    ]).lower()
    hay_tokens = _tokenise(haystack)
    matches: list[str] = []
    for construct in constructs:
        phrase = _clean(construct).lower()
        tokens = _tokenise(construct)
        if phrase and phrase in haystack:
            matches.append(construct)
        elif tokens and len(tokens & hay_tokens) >= max(1, min(2, len(tokens))):
            matches.append(construct)
    return matches[:5]


def _dataset_relevance(record: dict[str, Any], constructs: list[str], topic: str) -> float:
    matches = _matched_constructs(record, constructs)
    topic_tokens = _tokenise(topic)
    hay_tokens = _tokenise(" ".join([
        _clean(record.get("name")),
        _clean(record.get("description")),
        " ".join(record.get("subjects") or []),
    ]))
    return float(len(matches) * 8 + len(topic_tokens & hay_tokens) * 2 + (2 if record.get("doi") else 0))


def _official_portal_matches(payload: dict[str, Any], idea: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    constructs = _constructs_for_idea(idea)
    search_text = " ".join([
        _clean(payload.get("research_area")),
        _clean(payload.get("country_region")),
        _clean(payload.get("context")),
        *constructs,
    ])
    search_tokens = _tokenise(search_text)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for portal in OFFICIAL_DATA_PORTALS:
        tag_tokens = _tokenise(" ".join(portal.get("tags") or []))
        overlap = search_tokens & tag_tokens
        phrase_hits = sum(1 for tag in portal.get("tags") or [] if _clean(tag).lower() in search_text.lower())
        score = len(overlap) * 2 + phrase_hits * 3
        if score > 0:
            item = {k: v for k, v in portal.items() if k != "tags"}
            item["source_type"] = "Official data portal"
            item["discovery_database"] = "ProjectReady official-source catalogue"
            item["matched_variables_or_constructs"] = _matched_constructs(item, constructs) or constructs[:2]
            ranked.append((float(score), item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def _instrument_query(payload: dict[str, Any], constructs: list[str], systematic: bool) -> str:
    topic = _clean(payload.get("research_area"))
    context = _clean(payload.get("country_region"))
    if systematic:
        suffix = "systematic review protocol critical appraisal checklist quality assessment tool"
    else:
        methodology = _clean(payload.get("methodology")).lower()
        if "qualitative" in methodology or "case study" in methodology:
            suffix = "interview guide interview protocol qualitative instrument"
        elif "mixed" in methodology:
            suffix = "questionnaire scale validation interview guide instrument"
        else:
            suffix = "questionnaire scale instrument validation psychometric"
    query = " ".join([topic, *constructs[:4], context, suffix])
    return re.sub(r"\s+", " ", query).strip()[:220]


def _instrument_record_candidates(search_result: dict[str, Any]) -> list[dict[str, Any]]:
    records = search_result.get("sources") or []
    strong: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for record in records:
        haystack = " ".join([
            _clean(record.get("title")),
            _clean(record.get("abstract")),
            _clean(record.get("type")),
        ])
        prepared = {
            "title": _clean(record.get("title")),
            "authors": record.get("authors") or [],
            "year": record.get("year") or "",
            "source": _clean(record.get("source")),
            "doi": _clean(record.get("doi")),
            "url": _clean(record.get("url")) or (f"https://doi.org/{_clean(record.get('doi'))}" if record.get("doi") else ""),
            "abstract": _clean(record.get("abstract"))[:500],
            "database": _clean(record.get("database")),
            "record_type": "Candidate instrument or protocol source",
            "access_and_adaptation_note": (
                "Open the original publication and any supplement. Confirm the exact items, scoring, reliability, validity, population fit, "
                "translation requirements and copyright or permission conditions before adopting or adapting the instrument."
            ),
        }
        if _INSTRUMENT_TERMS.search(haystack):
            strong.append(prepared)
        else:
            other.append(prepared)
    # Return only records whose title, abstract or type explicitly signals an instrument,
    # scale, questionnaire, protocol or validation source. This prevents ordinary topical
    # papers from being misrepresented as adoptable instruments.
    return strong[:MAX_INSTRUMENT_RESULTS]


def _instrument_relevance(record: dict[str, Any], constructs: list[str], topic: str) -> float:
    haystack = " ".join([
        _clean(record.get("title")),
        _clean(record.get("abstract")),
        _clean(record.get("source")),
    ])
    matches = _matched_constructs(record, constructs)
    score = len(matches) * 8 + len(_tokenise(topic) & _tokenise(haystack)) * 2
    if _INSTRUMENT_TERMS.search(haystack):
        score += 6
    if record.get("doi"):
        score += 2
    return float(score)


def discover_research_resources(
    payload: dict[str, Any],
    ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Search once per resource type and map candidates to every generated idea.

    This avoids a slow provider search for every idea while still matching results to each idea's
    variables or constructs. Returned resources are candidates, not endorsements. Users must
    verify access, measurement fit, licensing, ethics and institutional requirements.
    """
    modes = research_resource_modes(payload)
    constructs = _global_construct_pool(payload, ideas)
    topic = _clean(payload.get("research_area"))
    provider_errors: list[dict[str, str]] = []
    live_datasets: list[dict[str, Any]] = []
    instrument_records: list[dict[str, Any]] = []
    dataset_query = ""
    instrument_query = ""
    searched_databases: list[str] = []

    if modes["secondary"]:
        dataset_query = _dataset_query(payload, constructs)
        for label, searcher in [
            ("DataCite", _search_datacite_datasets),
            ("Harvard Dataverse", _search_harvard_dataverse),
        ]:
            try:
                live_datasets.extend(searcher(dataset_query, MAX_DATASET_RESULTS))
                searched_databases.append(label)
            except Exception as exc:
                provider_errors.append({"provider": label, "error": _clean(exc)[:220]})
        live_datasets = _dedupe_dataset_candidates(live_datasets)

    if modes["instrument"]:
        instrument_query = _instrument_query(payload, constructs, modes["systematic"])
        try:
            instrument_search = search_literature_sources(
                profile={
                    "title": topic,
                    "research_area": topic,
                    "study_context": _clean(payload.get("context")),
                    "objectives": constructs[:4],
                },
                query=instrument_query,
                max_results=max(10, MAX_INSTRUMENT_RESULTS * 2),
                include_older_foundational=True,
            )
            instrument_records = _instrument_record_candidates(instrument_search)
            searched_databases.extend(instrument_search.get("databases") or [])
            provider_errors.extend(instrument_search.get("provider_errors") or [])
        except Exception as exc:
            provider_errors.append({"provider": "instrument literature search", "error": _clean(exc)[:220]})

    enriched: list[dict[str, Any]] = []
    for idea in ideas:
        item = dict(idea)
        idea_constructs = _constructs_for_idea(item)

        ranked_live = sorted(
            live_datasets,
            key=lambda record: _dataset_relevance(record, idea_constructs, topic),
            reverse=True,
        )
        selected_live: list[dict[str, Any]] = []
        for record in ranked_live[:5]:
            candidate = dict(record)
            candidate["matched_variables_or_constructs"] = _matched_constructs(record, idea_constructs) or idea_constructs[:2]
            selected_live.append(candidate)
        official = _official_portal_matches(payload, item, limit=5) if modes["secondary"] else []
        secondary_sources = _dedupe_dataset_candidates(selected_live + official)[:8]

        ranked_instruments = sorted(
            instrument_records,
            key=lambda record: _instrument_relevance(record, idea_constructs, topic),
            reverse=True,
        )
        selected_instruments: list[dict[str, Any]] = []
        for record in ranked_instruments[:6]:
            candidate = dict(record)
            candidate["matched_constructs"] = _matched_constructs(record, idea_constructs) or idea_constructs[:2]
            if modes["systematic"]:
                candidate["candidate_use"] = "Possible source of a review protocol, appraisal checklist or evidence-assessment tool relevant to the proposed review."
            elif "qualitative" in _clean(payload.get("methodology")).lower() or "case study" in _clean(payload.get("methodology")).lower():
                candidate["candidate_use"] = "Possible source of an interview guide, interview protocol or qualitative data-collection structure that may be adapted."
            else:
                candidate["candidate_use"] = "Possible source of a questionnaire, scale, index or measurement instrument that may be adopted or adapted."
            selected_instruments.append(candidate)

        existing_categories = item.get("possible_data_sources") or []
        if not isinstance(existing_categories, list):
            existing_categories = [existing_categories]
        if modes["secondary"] and secondary_sources:
            item["possible_data_sources"] = [source.get("name") for source in secondary_sources[:5] if source.get("name")]
        else:
            item["possible_data_sources"] = [str(x) for x in existing_categories if str(x).strip()]

        item["research_resource_guidance"] = {
            "search_basis": idea_constructs,
            "secondary_data_sources": secondary_sources,
            "questionnaire_or_instrument_sources": selected_instruments,
            "resource_note": (
                "These are candidate sources identified from live metadata searches and an official-source catalogue. "
                "Before approval, confirm variable definitions, coverage, access conditions, measurement validity, permissions, ethics and fit with the final design."
            ),
        }
        enriched.append(item)

    return {
        "ideas": enriched,
        "resource_search": {
            "searched_at": datetime.now(timezone.utc).isoformat(),
            "modes": modes,
            "dataset_query": dataset_query,
            "instrument_query": instrument_query,
            "databases": list(dict.fromkeys(searched_databases)),
            "provider_errors": provider_errors,
        },
    }
