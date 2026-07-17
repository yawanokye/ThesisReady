from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.source_finder import search_literature_sources

RESOURCE_TIMEOUT_SECONDS = max(4, int(os.getenv("TOPIC_RESOURCE_SEARCH_TIMEOUT_SECONDS", "10") or 10))
MAX_DATASET_RESULTS = max(2, min(int(os.getenv("TOPIC_DATASET_RESULTS", "6") or 6), 10))
MAX_INSTRUMENT_RESULTS = max(2, min(int(os.getenv("TOPIC_INSTRUMENT_RESULTS", "6") or 6), 10))
MAX_TOPIC_SPECIFIC_RESULTS = max(1, min(int(os.getenv("TOPIC_SPECIFIC_RESOURCE_RESULTS", "4") or 4), 6))
MIN_DATASET_RELEVANCE = float(os.getenv("TOPIC_DATASET_MIN_RELEVANCE", "22") or 22)
MIN_INSTRUMENT_RELEVANCE = float(os.getenv("TOPIC_INSTRUMENT_MIN_RELEVANCE", "18") or 18)

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
        "this", "that", "these", "those", "their", "there", "which", "where", "when", "what", "will", "would",
        "could", "should", "have", "has", "had", "are", "were", "was", "been", "being", "use", "using", "used",
        "level", "levels", "relevant", "records", "data", "dataset", "research", "results", "across", "overall",
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


def _idea_topic_scope(payload: dict[str, Any], idea: dict[str, Any]) -> dict[str, Any]:
    """Build a narrow search scope for one generated idea."""
    title = _clean(idea.get("title")) or _clean(payload.get("research_area"))
    synopsis = _clean(idea.get("synopsis"))
    constructs = _constructs_for_idea(idea)
    objectives = idea.get("proposed_objectives") or {}
    objective_values = (
        objectives.get("specific_objectives") or []
        if isinstance(objectives, dict)
        else []
    )
    if not isinstance(objective_values, list):
        objective_values = [objective_values]
    objective_values = [_clean(x) for x in objective_values if _clean(x)]
    context = _clean(payload.get("context"))
    country_region = _clean(payload.get("country_region"))
    topic_terms = _tokenise(" ".join([title, synopsis, *constructs, *objective_values[:3]]))
    geography_terms = _tokenise(" ".join([context, country_region]))
    return {
        "title": title,
        "synopsis": synopsis,
        "constructs": constructs,
        "objectives": objective_values[:3],
        "context": context,
        "country_region": country_region,
        "topic_terms": topic_terms,
        "subject_terms": topic_terms - geography_terms,
    }


def _specific_search_basis(scope: dict[str, Any]) -> list[str]:
    basis: list[str] = []
    for value in [scope.get("title"), *(scope.get("constructs") or [])]:
        text = _clean(value)
        if text and text.lower() not in {item.lower() for item in basis}:
            basis.append(text)
    return basis[:7]


def research_resource_modes(payload: dict[str, Any]) -> dict[str, bool]:
    methodology = _clean(payload.get("methodology")).lower()
    data_type = _clean(payload.get("data_type")).lower()

    systematic = "systematic literature review" in methodology
    # Secondary-data discovery is opt-in. A primary survey, qualitative study or
    # an undecided data-access selection should not trigger broad repository searches.
    # This prevents a topical word such as "training" or "performance" from pulling
    # unrelated datasets into an otherwise primary-data idea.
    secondary = (
        methodology in _SECONDARY_METHOD_TERMS
        or any(term in methodology for term in ["secondary", "econometric", "time-series", "panel data"])
        or "secondary data available" in data_type
        or "both primary and secondary" in data_type
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


def _dataset_query(payload: dict[str, Any], scope: dict[str, Any]) -> str:
    constructs = scope.get("constructs") or []
    pieces = [
        _clean(scope.get("title")),
        *constructs[:4],
        _clean(scope.get("country_region")),
        _clean(scope.get("context")),
    ]
    query = " ".join(x for x in pieces if x)
    return re.sub(r"\s+", " ", query).strip()[:260]


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


_GENERIC_RESOURCE_TERMS = {
    "employee", "employees", "staff", "worker", "workers", "administrative", "administration", "public", "service",
    "services", "support", "development", "training", "performance", "competence", "competency", "knowledge", "skills",
    "work", "workplace", "job", "professional", "participation", "opportunity", "opportunities", "quality", "practice",
    "practices", "management", "institution", "institutional", "organisation", "organization", "university", "ghana",
}


def _exact_construct_matches(record: dict[str, Any], constructs: list[str]) -> list[str]:
    haystack = " ".join([
        _clean(record.get("name") or record.get("title")),
        _clean(record.get("description") or record.get("abstract")),
        " ".join(record.get("subjects") or []),
    ]).lower()
    exact: list[str] = []
    for construct in constructs:
        phrase = _clean(construct).lower()
        if not phrase:
            continue
        # Single generic words are too weak to validate a dataset. Multiword
        # constructs such as "employee competence" or "administrative performance"
        # carry much more topic information and may qualify as exact matches.
        tokens = _tokenise(construct)
        if phrase in haystack and (len(tokens) >= 2 or not tokens.issubset(_GENERIC_RESOURCE_TERMS)):
            exact.append(construct)
    return exact[:5]


def _specific_overlap(record: dict[str, Any], scope: dict[str, Any]) -> set[str]:
    hay_tokens = _tokenise(" ".join([
        _clean(record.get("name") or record.get("title")),
        _clean(record.get("description") or record.get("abstract")),
        " ".join(record.get("subjects") or []),
    ]))
    topic_terms = set(scope.get("subject_terms") or set()) - _GENERIC_RESOURCE_TERMS
    return topic_terms & hay_tokens


def _context_overlap(record: dict[str, Any], scope: dict[str, Any]) -> set[str]:
    hay_tokens = _tokenise(" ".join([
        _clean(record.get("name") or record.get("title")),
        _clean(record.get("description") or record.get("abstract")),
        " ".join(record.get("subjects") or []),
    ]))
    context_tokens = _tokenise(" ".join([
        _clean(scope.get("context")),
        _clean(scope.get("country_region")),
    ]))
    return context_tokens & hay_tokens


def _dataset_relevance(record: dict[str, Any], scope: dict[str, Any]) -> float:
    constructs = scope.get("constructs") or []
    exact_matches = _exact_construct_matches(record, constructs)
    matched_constructs = _matched_constructs(record, constructs)
    specific_overlap = _specific_overlap(record, scope)
    context_overlap = _context_overlap(record, scope)
    title_overlap = (_tokenise(scope.get("title")) - _GENERIC_RESOURCE_TERMS) & _tokenise(" ".join([
        _clean(record.get("name")),
        _clean(record.get("description")),
        " ".join(record.get("subjects") or []),
    ]))
    return float(
        len(exact_matches) * 18
        + len(matched_constructs) * 5
        + len(specific_overlap) * 5
        + len(context_overlap) * 4
        + len(title_overlap) * 3
        + (1 if record.get("doi") else 0)
    )


def _dataset_is_topic_specific(record: dict[str, Any], scope: dict[str, Any]) -> bool:
    constructs = scope.get("constructs") or []
    exact_matches = _exact_construct_matches(record, constructs)
    specific_overlap = _specific_overlap(record, scope)
    context_overlap = _context_overlap(record, scope)

    # A dataset must match a meaningful multiword construct, or combine several
    # specific topic terms with the proposed population/geographic context. Generic
    # words such as employee, development or performance cannot qualify on their own.
    if exact_matches:
        return bool(context_overlap or len(specific_overlap) >= 1)
    return len(specific_overlap) >= 3 and len(context_overlap) >= 1


def _official_portal_matches(payload: dict[str, Any], idea: dict[str, Any], limit: int = MAX_TOPIC_SPECIFIC_RESULTS) -> list[dict[str, Any]]:
    scope = _idea_topic_scope(payload, idea)
    constructs = scope.get("constructs") or []
    subject_terms = set(scope.get("subject_terms") or set())
    ranked: list[tuple[float, dict[str, Any]]] = []
    for portal in OFFICIAL_DATA_PORTALS:
        portal_text = " ".join([
            _clean(portal.get("name")),
            _clean(portal.get("description")),
            " ".join(portal.get("tags") or []),
        ])
        portal_tokens = _tokenise(portal_text)
        overlap = (subject_terms - _GENERIC_RESOURCE_TERMS) & portal_tokens
        matched_constructs = _exact_construct_matches(portal, constructs)
        context_tokens = _tokenise(" ".join([_clean(scope.get("context")), _clean(scope.get("country_region"))]))
        context_match = context_tokens & portal_tokens
        if not matched_constructs and len(overlap) < 3:
            continue
        if context_tokens and not context_match and not matched_constructs:
            continue
        score = len(overlap) * 5 + len(matched_constructs) * 18 + len(context_match) * 3
        item = {k: v for k, v in portal.items() if k != "tags"}
        item["source_type"] = "Official data portal"
        item["discovery_database"] = "ProjectReady official-source catalogue"
        item["matched_variables_or_constructs"] = matched_constructs
        item["matched_topic_terms"] = sorted(overlap)[:6]
        item["topic_match_reason"] = "Matched this idea's focal constructs and subject terms."
        ranked.append((float(score), item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def _instrument_query(payload: dict[str, Any], scope: dict[str, Any], systematic: bool) -> str:
    topic = _clean(scope.get("title"))
    constructs = scope.get("constructs") or []
    context = _clean(scope.get("country_region"))
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
    return re.sub(r"\s+", " ", query).strip()[:260]


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


def _instrument_relevance(record: dict[str, Any], scope: dict[str, Any]) -> float:
    haystack = " ".join([
        _clean(record.get("title")),
        _clean(record.get("abstract")),
        _clean(record.get("source")),
    ])
    matches = _matched_constructs(record, scope.get("constructs") or [])
    subject_overlap = set(scope.get("subject_terms") or set()) & _tokenise(haystack)
    score = len(matches) * 8 + len(subject_overlap) * 2
    if _INSTRUMENT_TERMS.search(haystack):
        score += 6
    if record.get("doi"):
        score += 1
    return float(score)


def _instrument_is_topic_specific(record: dict[str, Any], scope: dict[str, Any]) -> bool:
    haystack = " ".join([
        _clean(record.get("title")),
        _clean(record.get("abstract")),
        _clean(record.get("source")),
    ])
    if not _INSTRUMENT_TERMS.search(haystack):
        return False
    matches = _matched_constructs(record, scope.get("constructs") or [])
    subject_overlap = set(scope.get("subject_terms") or set()) & _tokenise(haystack)
    return bool(matches) or len(subject_overlap) >= 2


def _topic_specific_data_directions(
    payload: dict[str, Any],
    idea: dict[str, Any],
    modes: dict[str, bool],
    secondary_sources: list[dict[str, Any]],
    instrument_sources: list[dict[str, Any]],
) -> list[str]:
    scope = _idea_topic_scope(payload, idea)
    constructs = scope.get("constructs") or []
    focal = ", ".join(constructs[:3]) or _clean(scope.get("title"))
    population = _clean(scope.get("context")) or "the proposed study population"
    place = _clean(scope.get("country_region"))
    location = f" in {place}" if place else ""
    methodology = _clean(payload.get("methodology")).lower()
    directions: list[str] = []

    if modes.get("secondary"):
        for source in secondary_sources[:3]:
            name = _clean(source.get("name"))
            matches = source.get("matched_variables_or_constructs") or []
            match_text = ", ".join(str(x) for x in matches[:3] if str(x).strip())
            if name:
                directions.append(f"{name} records relevant to {match_text or focal}{location}")
        # Do not manufacture a vague secondary-data recommendation. When the
        # strict gate finds nothing useful, omit the secondary-data direction.

    if modes.get("instrument"):
        if modes.get("systematic"):
            directions.append(f"Peer-reviewed studies and review records specifically addressing {_clean(scope.get('title'))}")
        elif "qualitative" in methodology or "case study" in methodology:
            directions.append(f"Semi-structured interview data from {population}{location} focused on {focal}")
        elif "mixed" in methodology:
            directions.append(f"Questionnaire responses and interview data from {population}{location} measuring or exploring {focal}")
        else:
            directions.append(f"Primary questionnaire responses from {population}{location} measuring {focal}")

    for source in instrument_sources[:2]:
        title = _clean(source.get("title"))
        matches = source.get("matched_constructs") or []
        if title:
            directions.append(f"Candidate items or measures from {title}, subject to validation for {', '.join(matches[:3]) or focal}")

    output: list[str] = []
    seen: set[str] = set()
    for item in directions:
        key = item.lower()
        if item and key not in seen:
            output.append(item)
            seen.add(key)
    return output[:6]


def discover_research_resources(
    payload: dict[str, Any],
    ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Find narrowly matched data and instrument candidates for each idea."""
    modes = research_resource_modes(payload)
    provider_errors: list[dict[str, str]] = []
    searched_databases: list[str] = []
    per_idea_searches: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    dataset_cache: dict[str, list[dict[str, Any]]] = {}
    instrument_cache: dict[str, tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]] = {}

    for idea_index, idea in enumerate(ideas, start=1):
        item = dict(idea)
        scope = _idea_topic_scope(payload, item)
        idea_constructs = scope.get("constructs") or []
        dataset_query = ""
        instrument_query = ""
        live_datasets: list[dict[str, Any]] = []
        instrument_records: list[dict[str, Any]] = []
        idea_databases: list[str] = []

        if modes["secondary"]:
            dataset_query = _dataset_query(payload, scope)
            cache_key = dataset_query.lower()
            if cache_key in dataset_cache:
                live_datasets = dataset_cache[cache_key]
            else:
                datacite_records: list[dict[str, Any]] = []
                try:
                    datacite_records = _search_datacite_datasets(dataset_query, MAX_DATASET_RESULTS)
                    idea_databases.append("DataCite")
                except Exception as exc:
                    provider_errors.append({"provider": "DataCite", "idea": _clean(scope.get("title"))[:180], "error": _clean(exc)[:220]})
                specific_datacite = [record for record in datacite_records if _dataset_is_topic_specific(record, scope) and _dataset_relevance(record, scope) >= MIN_DATASET_RELEVANCE]
                dataverse_records: list[dict[str, Any]] = []
                if len(specific_datacite) < 2:
                    try:
                        dataverse_records = _search_harvard_dataverse(dataset_query, MAX_DATASET_RESULTS)
                        idea_databases.append("Harvard Dataverse")
                    except Exception as exc:
                        provider_errors.append({"provider": "Harvard Dataverse", "idea": _clean(scope.get("title"))[:180], "error": _clean(exc)[:220]})
                live_datasets = _dedupe_dataset_candidates(datacite_records + dataverse_records)
                dataset_cache[cache_key] = live_datasets

        if modes["instrument"]:
            instrument_query = _instrument_query(payload, scope, modes["systematic"])
            cache_key = instrument_query.lower()
            if cache_key in instrument_cache:
                instrument_records, cached_databases, cached_errors = instrument_cache[cache_key]
                idea_databases.extend(cached_databases)
                provider_errors.extend(cached_errors)
            else:
                local_errors: list[dict[str, str]] = []
                local_databases: list[str] = []
                try:
                    instrument_search = search_literature_sources(
                        profile={
                            "title": _clean(scope.get("title")),
                            "research_area": _clean(scope.get("title")),
                            "study_context": " ".join(filter(None, [_clean(scope.get("context")), _clean(scope.get("country_region"))])),
                            "objectives": idea_constructs[:4],
                        },
                        query=instrument_query,
                        max_results=max(8, MAX_INSTRUMENT_RESULTS * 2),
                        include_older_foundational=True,
                    )
                    instrument_records = _instrument_record_candidates(instrument_search)
                    local_databases.extend(instrument_search.get("databases") or [])
                    for error in instrument_search.get("provider_errors") or []:
                        prepared = dict(error)
                        prepared["idea"] = _clean(scope.get("title"))[:180]
                        local_errors.append(prepared)
                except Exception as exc:
                    local_errors.append({"provider": "instrument literature search", "idea": _clean(scope.get("title"))[:180], "error": _clean(exc)[:220]})
                instrument_cache[cache_key] = (instrument_records, local_databases, local_errors)
                idea_databases.extend(local_databases)
                provider_errors.extend(local_errors)

        ranked_live = sorted(
            [record for record in live_datasets if _dataset_is_topic_specific(record, scope) and _dataset_relevance(record, scope) >= MIN_DATASET_RELEVANCE],
            key=lambda record: _dataset_relevance(record, scope),
            reverse=True,
        )
        selected_live: list[dict[str, Any]] = []
        for record in ranked_live[:MAX_TOPIC_SPECIFIC_RESULTS]:
            candidate = dict(record)
            candidate["matched_variables_or_constructs"] = _matched_constructs(record, idea_constructs)
            candidate["matched_topic_terms"] = sorted(set(scope.get("subject_terms") or set()) & _tokenise(" ".join([_clean(record.get("name")), _clean(record.get("description")), " ".join(record.get("subjects") or [])])))[:6]
            candidate["topic_relevance_score"] = _dataset_relevance(record, scope)
            candidate["topic_match_reason"] = "Passed the idea-specific dataset relevance gate."
            selected_live.append(candidate)

        official = _official_portal_matches(payload, item) if modes["secondary"] else []
        secondary_sources = _dedupe_dataset_candidates(selected_live + official)[:MAX_TOPIC_SPECIFIC_RESULTS]

        ranked_instruments = sorted(
            [record for record in instrument_records if _instrument_is_topic_specific(record, scope) and _instrument_relevance(record, scope) >= MIN_INSTRUMENT_RELEVANCE],
            key=lambda record: _instrument_relevance(record, scope),
            reverse=True,
        )
        selected_instruments: list[dict[str, Any]] = []
        for record in ranked_instruments[:MAX_TOPIC_SPECIFIC_RESULTS]:
            candidate = dict(record)
            candidate["matched_constructs"] = _matched_constructs(record, idea_constructs)
            candidate["matched_topic_terms"] = sorted(set(scope.get("subject_terms") or set()) & _tokenise(" ".join([_clean(record.get("title")), _clean(record.get("abstract"))])))[:6]
            candidate["topic_relevance_score"] = _instrument_relevance(record, scope)
            candidate["topic_match_reason"] = "Passed the idea-specific instrument relevance gate."
            if modes["systematic"]:
                candidate["candidate_use"] = "Possible source of a review protocol, appraisal checklist or evidence-assessment tool specifically relevant to this proposed review."
            elif "qualitative" in _clean(payload.get("methodology")).lower() or "case study" in _clean(payload.get("methodology")).lower():
                candidate["candidate_use"] = "Possible source of an interview guide or qualitative data-collection structure for the focal constructs in this idea."
            else:
                candidate["candidate_use"] = "Possible source of a questionnaire, scale, index or measurement instrument for the focal constructs in this idea."
            selected_instruments.append(candidate)

        item["possible_data_sources"] = _topic_specific_data_directions(payload, item, modes, secondary_sources, selected_instruments)
        item["research_resource_guidance"] = {
            "topic_scope": _clean(scope.get("title")),
            "search_basis": _specific_search_basis(scope),
            "dataset_query": dataset_query,
            "instrument_query": instrument_query,
            "secondary_data_sources": secondary_sources,
            "questionnaire_or_instrument_sources": selected_instruments,
            "show_secondary_data": bool(modes.get("secondary") and secondary_sources),
            "show_instruments": bool(modes.get("instrument") and selected_instruments),
            "resource_note": "Only strongly matched candidates are shown. If no defensible source is found, the section is omitted rather than filled with a general or weakly related record. Confirm variables, population, access conditions, validity, permissions and ethics before use.",
        }
        enriched.append(item)
        searched_databases.extend(idea_databases)
        per_idea_searches.append({
            "idea_number": idea_index,
            "title": _clean(scope.get("title")),
            "dataset_query": dataset_query,
            "instrument_query": instrument_query,
            "datasets_returned": len(secondary_sources),
            "instruments_returned": len(selected_instruments),
        })

    return {
        "ideas": enriched,
        "resource_search": {
            "searched_at": datetime.now(timezone.utc).isoformat(),
            "modes": modes,
            "strategy": "per_idea_strict",
            "per_idea_searches": per_idea_searches,
            "databases": list(dict.fromkeys(searched_databases)),
            "provider_errors": provider_errors,
        },
    }
