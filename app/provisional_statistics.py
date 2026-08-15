from __future__ import annotations

import hashlib
import re
from typing import Any

_NUMERIC_SIGNAL_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:percent|percentage|million|billion|thousand|"
    r"years?|months?|days?|respondents?|participants?|households?|firms?|students?|workers?|cases?|"
    r"kg|km|usd|ghs|cedis?|dollars?|people|persons)\b)",
    flags=re.IGNORECASE,
)
_YEAR_ONLY_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _source_key(source: dict[str, Any]) -> str:
    doi = _clean(source.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9]+", "", _clean(source.get("title")).lower())[:140]
    return f"title:{title}" if title else ""


def _structured_sources(profile: dict[str, Any]) -> list[dict[str, Any]]:
    collections: list[list[dict[str, Any]]] = []
    bank = profile.get("source_bank") or []
    if isinstance(bank, list):
        collections.append([x for x in bank if isinstance(x, dict)])
    retrieved = profile.get("retrieved_sources") or {}
    if isinstance(retrieved, dict) and isinstance(retrieved.get("sources"), list):
        collections.append([x for x in retrieved.get("sources") or [] if isinstance(x, dict)])

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        for source in collection:
            key = _source_key(source)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(source)
    return out


def _source_locator(source: dict[str, Any]) -> str:
    doi = _clean(source.get("doi"))
    if doi:
        return f"https://doi.org/{doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/')}"
    return _clean(source.get("url") or source.get("landing_page_url") or source.get("openalex_url"))


def _source_label(source: dict[str, Any]) -> str:
    hint = _clean(source.get("apa_hint"))
    if hint:
        return hint[:320]
    authors = source.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    author = _clean(authors[0]) if authors else ""
    year = _clean(source.get("year"))
    title = _clean(source.get("title"))
    parts = [x for x in [author + (f" ({year})" if year else ""), title] if x]
    return ". ".join(parts)[:320]


def _numeric_sentences(source: dict[str, Any]) -> list[str]:
    # Only inspect fields that may carry source-provided substantive content.
    raw = _clean(source.get("evidence_excerpt") or source.get("abstract") or source.get("description") or source.get("snippet"))
    if not raw:
        return []
    output: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(raw):
        sentence = _clean(sentence)
        if len(sentence) < 35 or len(sentence) > 420:
            continue
        if not _NUMERIC_SIGNAL_RE.search(sentence):
            continue
        # A sentence containing only a publication year is not a statistical fact.
        without_years = _YEAR_ONLY_RE.sub("", sentence)
        if not re.search(r"\d", without_years):
            continue
        output.append(sentence)
    return output[:3]


def discover_provisional_statistics(profile: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    """Return source-grounded numerical evidence candidates for user confirmation.

    No statistic is invented here. Candidates are extracted only from substantive
    text returned with a structured source record and must have a DOI or stable URL.
    """
    confirmations = profile.get("provisional_statistics_confirmations") or {}
    if not isinstance(confirmations, dict):
        confirmations = {}
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in _structured_sources(profile):
        locator = _source_locator(source)
        if not locator:
            continue
        label = _source_label(source)
        for sentence in _numeric_sentences(source):
            identity = hashlib.sha256(f"{_source_key(source)}|{sentence}".encode("utf-8")).hexdigest()[:16]
            if identity in seen:
                continue
            seen.add(identity)
            status = str(confirmations.get(identity) or "pending").strip().lower()
            if status not in {"pending", "confirmed", "rejected"}:
                status = "pending"
            candidates.append({
                "id": identity,
                "statement": sentence,
                "source_label": label,
                "source_locator": locator,
                "source_title": _clean(source.get("title")),
                "source_year": _clean(source.get("year")),
                "status": status,
                "confirmation_required": status != "confirmed",
                "usage_rule": (
                    "This numerical statement came from accessible source text. Keep it provisional and visibly marked "
                    "for confirmation until the student verifies the source and context."
                ),
            })
            if len(candidates) >= max(1, int(limit)):
                return candidates
    return candidates


def refresh_provisional_statistics(profile: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    candidates = discover_provisional_statistics(profile, limit=limit)
    profile["provisional_statistics"] = candidates
    return candidates


def confirmed_statistic_ids(profile: dict[str, Any]) -> set[str]:
    confirmations = profile.get("provisional_statistics_confirmations") or {}
    if not isinstance(confirmations, dict):
        return set()
    return {str(key) for key, value in confirmations.items() if str(value).lower() == "confirmed"}


def provisional_statistic_prompt_context(profile: dict[str, Any]) -> dict[str, Any]:
    candidates = refresh_provisional_statistics(profile)
    return {
        "candidates": candidates,
        "rules": [
            "Never invent a statistic, percentage, count, rate, date-specific value, coefficient or sample figure.",
            "Use a numerical claim only when it is explicitly present in a user-supplied source or in one of these source-grounded candidates.",
            "For every pending candidate used in the chapter, put the complete statement on a separate line in this exact form: [CONFIRM SOURCED STATISTIC: <statement> | Source: <source_label> | <source_locator>].",
            "The confirmation marker must remain in square brackets so the DOCX renders it red and the student sees that verification is still required.",
            "Do not convert a pending sourced statistic into ordinary black prose until the student has confirmed it.",
            "A bibliographic record, title or abstract does not justify a more detailed numerical claim than the accessible source text actually states.",
            "If no suitable source-grounded statistic is available, use [PROVIDE VERIFIED STATISTIC AND SOURCE: describe the needed statistic] rather than guessing.",
        ],
    }
