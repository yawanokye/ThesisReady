from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.chapter_file_extractor import extract_uploaded_text

MAX_SELECTED_PAPERS = max(1, min(50, int(os.getenv("PROJECTREADY_MAX_SELECTED_PAPERS", "50") or 50)))
MAX_SELECTED_PAPERS_TOTAL_BYTES = max(25 * 1024 * 1024, int(os.getenv("PROJECTREADY_SELECTED_PAPERS_TOTAL_BYTES", str(250 * 1024 * 1024)) or (250 * 1024 * 1024)))
MAX_SELECTED_PAPER_EVIDENCE_CHARS = max(
    8000,
    min(40000, int(os.getenv("PROJECTREADY_SELECTED_PAPER_EVIDENCE_CHARS", "26000") or 26000)),
)
_METADATA_TIMEOUT = max(2, min(15, int(os.getenv("PROJECTREADY_SELECTED_PAPER_METADATA_TIMEOUT_SECONDS", "7") or 7)))
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".rtf"}
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalise_doi(value: Any) -> str:
    doi = _clean(value)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi\s*:\s*", "", doi, flags=re.I)
    return doi.rstrip(".,;:)]}>").strip()


def _extract_doi(text: str) -> str:
    match = _DOI_RE.search(str(text or "")[:60000])
    return _normalise_doi(match.group(0)) if match else ""


def _candidate_title(text: str, filename: str) -> str:
    lines = []
    for raw in str(text or "")[:8000].splitlines():
        line = _clean(raw)
        if not line or re.fullmatch(r"\[Page\s+\d+\]", line, flags=re.I):
            continue
        if line.lower() in {"abstract", "introduction", "article", "research article", "original article"}:
            continue
        if "doi.org/" in line.lower() or line.lower().startswith("doi:") or line.lower().startswith("http"):
            continue
        if len(line) < 18 or len(line) > 260:
            continue
        if len(_YEAR_RE.findall(line)) > 2:
            continue
        lines.append(line)
        if len(lines) >= 12:
            break
    if lines:
        # Article titles are often one of the longest early lines. This is only a
        # candidate and never becomes citation-eligible until verified/confirmed.
        return max(lines[:8], key=len)[:260]
    base = os.path.splitext(os.path.basename(filename or "uploaded paper"))[0]
    return re.sub(r"[_-]+", " ", base).strip()[:260]


def _candidate_year(text: str) -> str:
    years = _YEAR_RE.findall(str(text or "")[:7000])
    if not years:
        return ""
    # Keep only a visible candidate. It is not trusted for citation until the
    # bibliographic record is verified or the user confirms it.
    current = datetime.now(timezone.utc).year + 1
    plausible = [int(y) for y in years if 1900 <= int(y) <= current]
    return str(max(plausible)) if plausible else ""


def _section_window(text: str, heading_pattern: str, span: int = 4200) -> str:
    match = re.search(heading_pattern, text, flags=re.I | re.M)
    if not match:
        return ""
    start = max(0, match.start() - 250)
    return text[start : start + span]


def evidence_excerpt(text: str) -> str:
    """Create a compact, broad excerpt that covers more than the first pages.

    The full extracted paper can be large. We keep a bounded evidence record with
    front matter plus method/results/discussion/conclusion windows when available.
    This gives later chapter stages access to the student's paper without sending
    all fifty complete files to the model on every request.
    """
    raw = str(text or "").strip()
    if len(raw) <= MAX_SELECTED_PAPER_EVIDENCE_CHARS:
        return raw
    pieces: list[str] = [raw[:8000]]
    patterns = [
        r"^\s*(?:\d+(?:\.\d+)*\s+)?(?:materials\s+and\s+methods|methodology|methods?)\b",
        r"^\s*(?:\d+(?:\.\d+)*\s+)?(?:results?|findings?)\b",
        r"^\s*(?:\d+(?:\.\d+)*\s+)?discussion\b",
        r"^\s*(?:\d+(?:\.\d+)*\s+)?conclusions?\b",
    ]
    for pattern in patterns:
        window = _section_window(raw, pattern)
        if window:
            pieces.append(window)
    pieces.append(raw[-4500:])
    out: list[str] = []
    seen: set[str] = set()
    total = 0
    for piece in pieces:
        cleaned = piece.strip()
        if not cleaned:
            continue
        key = re.sub(r"\W+", "", cleaned[:300].lower())
        if key in seen:
            continue
        seen.add(key)
        remaining = MAX_SELECTED_PAPER_EVIDENCE_CHARS - total
        if remaining <= 0:
            break
        clipped = cleaned[:remaining]
        out.append(clipped)
        total += len(clipped)
    return "\n\n--- selected paper evidence excerpt ---\n\n".join(out).strip()


def _crossref_metadata(doi: str) -> dict[str, Any] | None:
    clean_doi = _normalise_doi(doi)
    if not clean_doi:
        return None
    url = "https://api.crossref.org/works/" + quote(clean_doi, safe="")
    request = Request(
        url,
        headers={
            "User-Agent": "ProjectReadyAI/1.0 (selected-paper metadata verification)",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=_METADATA_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload.get("message") or {}
    if not isinstance(message, dict):
        return None
    titles = message.get("title") or []
    title = _clean(titles[0] if isinstance(titles, list) and titles else titles)
    authors: list[str] = []
    for author in message.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = _clean(" ".join(part for part in [_clean(author.get("given")), _clean(author.get("family"))] if part))
        if name:
            authors.append(name)
    if not authors:
        publisher = _clean(message.get("publisher"))
        if publisher:
            authors = [publisher]
    year = ""
    for date_key in ("published-print", "published-online", "published", "issued", "created"):
        date_obj = message.get(date_key) or {}
        parts = date_obj.get("date-parts") if isinstance(date_obj, dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            try:
                year = str(int(parts[0][0]))
                break
            except Exception:
                pass
    container = message.get("container-title") or []
    source = _clean(container[0] if isinstance(container, list) and container else container) or _clean(message.get("publisher"))
    resolved_doi = _normalise_doi(message.get("DOI") or clean_doi)
    locator = _clean(message.get("URL")) or (f"https://doi.org/{resolved_doi}" if resolved_doi else "")
    if not title or not authors or not year:
        return None
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "source": source,
        "doi": resolved_doi,
        "url": locator,
        "database": "Crossref",
    }


def _apa_hint(meta: dict[str, Any]) -> str:
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    author_text = ", ".join(_clean(author) for author in authors if _clean(author))
    year = _clean(meta.get("year"))
    title = _clean(meta.get("title"))
    source = _clean(meta.get("source"))
    doi = _normalise_doi(meta.get("doi"))
    pieces = []
    if author_text:
        pieces.append(author_text.rstrip("."))
    if year:
        pieces.append(f"({year}).")
    if title:
        pieces.append(title.rstrip(".") + ".")
    if source:
        pieces.append(source.rstrip(".") + ".")
    if doi:
        pieces.append(f"https://doi.org/{doi}")
    return " ".join(pieces).strip()


def build_selected_paper_record(filename: str, content: bytes) -> dict[str, Any]:
    extension = os.path.splitext(os.path.basename(str(filename or "")))[1].lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise ValueError("Selected papers must be PDF, DOCX, TXT, MD or RTF files.")
    extracted = extract_uploaded_text(filename, content)
    text = extracted.get("text") or ""
    doi = _extract_doi(text)
    verified_meta: dict[str, Any] | None = None
    verification_error = ""
    if doi:
        try:
            verified_meta = _crossref_metadata(doi)
        except Exception as exc:
            verification_error = str(exc)[:180]

    candidate = {
        "title": _candidate_title(text, extracted.get("filename") or filename),
        "authors": [],
        "year": _candidate_year(text),
        "source": "",
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else "",
    }
    meta = verified_meta or candidate
    verified = bool(verified_meta)
    record = {
        "id": str(uuid.uuid4()),
        "filename": extracted.get("filename") or os.path.basename(filename or "paper"),
        "extension": extracted.get("extension") or extension,
        "character_count": int(extracted.get("character_count") or 0),
        "truncated": bool(extracted.get("truncated")),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "attachment_origin": "uploaded_selected_paper",
        "user_uploaded_full_text": True,
        "metadata_verified": verified,
        "user_metadata_confirmed": False,
        "citation_eligible": verified,
        "metadata_status": "verified_crossref" if verified else "needs_user_confirmation",
        "verification_error": verification_error,
        "title": _clean(meta.get("title")),
        "authors": meta.get("authors") or [],
        "year": _clean(meta.get("year")),
        "source": _clean(meta.get("source")),
        "doi": _normalise_doi(meta.get("doi")),
        "url": _clean(meta.get("url")),
        "database": "User uploaded full text + Crossref" if verified else "User uploaded full text",
        "evidence_excerpt": evidence_excerpt(text),
        "relevance_tier": "unclassified",
        "relevance_reason": "Selected and uploaded by the student for this research project.",
        "suggested_use": "Prioritise where the uploaded full text directly supports the active claim or section.",
        "provenance_note": (
            "Full text was uploaded by the user. Citation metadata was verified against Crossref."
            if verified
            else "Full text was uploaded by the user. Bibliographic metadata must be confirmed before ProjectReady may create a new author-year citation from this paper."
        ),
    }
    if verified:
        record["apa_hint"] = _apa_hint(record)
        record["user_verified"] = True
    return record


def public_paper_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return UI-safe paper metadata without sending the stored evidence excerpt back."""
    return {
        key: record.get(key)
        for key in (
            "id", "filename", "extension", "character_count", "truncated", "uploaded_at",
            "metadata_verified", "user_metadata_confirmed", "citation_eligible", "metadata_status",
            "verification_error", "title", "authors", "year", "source", "doi", "url", "database",
            "relevance_tier", "relevance_reason", "suggested_use", "provenance_note",
        )
    }


def paper_to_source_record(paper: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(paper.get("citation_eligible")):
        return None
    title = _clean(paper.get("title"))
    authors = paper.get("authors") or []
    year = _clean(paper.get("year"))
    if isinstance(authors, str):
        authors = [authors]
    authors = [_clean(author) for author in authors if _clean(author)]
    if not title or not authors or not year:
        return None
    source = {
        "title": title,
        "authors": authors,
        "year": year,
        "source": _clean(paper.get("source")),
        "doi": _normalise_doi(paper.get("doi")),
        "url": _clean(paper.get("url")),
        "database": _clean(paper.get("database")) or "User uploaded full text",
        "apa_hint": _clean(paper.get("apa_hint")) or _apa_hint(paper),
        "attachment_origin": "uploaded_selected_paper",
        "selected_paper_id": _clean(paper.get("id")),
        "user_uploaded_full_text": True,
        "user_verified": True,
        "metadata_verified": bool(paper.get("metadata_verified")),
        "user_metadata_confirmed": bool(paper.get("user_metadata_confirmed")),
        "citation_eligible": True,
        "claim_support_eligible": True,
        "verification_basis": "User-uploaded full text with verified or user-confirmed bibliographic metadata",
        "evidence_excerpt": str(paper.get("evidence_excerpt") or "")[:MAX_SELECTED_PAPER_EVIDENCE_CHARS],
        "abstract": str(paper.get("evidence_excerpt") or "")[:1400],
        "relevance_tier": str(paper.get("relevance_tier") or "unclassified"),
        "relevance_reason": str(paper.get("relevance_reason") or "Selected and uploaded by the student."),
        "suggested_use": str(paper.get("suggested_use") or "Use where the uploaded full text directly supports the active claim."),
    }
    return source


def _source_identity(source: dict[str, Any]) -> str:
    doi = _normalise_doi(source.get("doi")).lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", _clean(source.get("title")).lower())[:140]
    return "title:" + title if title else ""


def sync_selected_papers_to_source_bank(profile: dict[str, Any], *, limit: int = 150) -> list[dict[str, Any]]:
    papers = profile.get("selected_papers") or []
    if not isinstance(papers, list):
        papers = []
    selected_sources = [paper_to_source_record(item) for item in papers if isinstance(item, dict)]
    selected_sources = [item for item in selected_sources if item]

    existing = profile.get("source_bank") or []
    if not isinstance(existing, list):
        existing = []
    # Remove old mirrors of selected papers before rebuilding them. User-selected
    # papers come first so they are retained if a combined bank hits its cap.
    existing = [
        item for item in existing
        if isinstance(item, dict) and str(item.get("attachment_origin") or "") != "uploaded_selected_paper"
    ]
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in [*selected_sources, *existing]:
        key = _source_identity(source)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(source)
        if len(merged) >= limit:
            break
    profile["source_bank"] = merged
    profile["selected_paper_summary"] = {
        "count": len(papers),
        "citation_ready": sum(1 for item in papers if isinstance(item, dict) and item.get("citation_eligible")),
        "needs_metadata_confirmation": sum(1 for item in papers if isinstance(item, dict) and not item.get("citation_eligible")),
        "maximum": MAX_SELECTED_PAPERS,
    }
    return merged


def update_selected_paper_metadata(paper: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    updated = dict(paper)
    doi = _normalise_doi(updates.get("doi") if "doi" in updates else updated.get("doi"))
    verified_meta: dict[str, Any] | None = None
    if doi:
        try:
            verified_meta = _crossref_metadata(doi)
        except Exception:
            verified_meta = None
    if verified_meta:
        updated.update(verified_meta)
        updated["metadata_verified"] = True
        updated["user_metadata_confirmed"] = bool(updates.get("confirm", True))
        updated["citation_eligible"] = True
        updated["metadata_status"] = "verified_crossref"
        updated["database"] = "User uploaded full text + Crossref"
        updated["provenance_note"] = "Full text was uploaded by the user. Citation metadata was verified against Crossref."
    else:
        for field in ("title", "year", "source", "url"):
            if field in updates:
                updated[field] = _clean(updates.get(field))
        if "doi" in updates:
            updated["doi"] = doi
        if "authors" in updates:
            raw_authors = updates.get("authors") or []
            if isinstance(raw_authors, str):
                raw_authors = re.split(r"\s*[;|]\s*|\n+", raw_authors)
                if len(raw_authors) == 1 and "," in raw_authors[0]:
                    raw_authors = [part.strip() for part in raw_authors[0].split(",") if part.strip()]
            updated["authors"] = [_clean(author) for author in raw_authors if _clean(author)]
        confirmed = bool(updates.get("confirm"))
        complete = bool(_clean(updated.get("title")) and updated.get("authors") and re.fullmatch(r"(?:19|20)\d{2}[a-z]?", _clean(updated.get("year")), flags=re.I))
        updated["user_metadata_confirmed"] = confirmed and complete
        updated["citation_eligible"] = confirmed and complete
        updated["metadata_status"] = "confirmed_by_user" if updated["citation_eligible"] else "needs_user_confirmation"
        updated["database"] = "User uploaded full text"
        updated["provenance_note"] = (
            "Full text and bibliographic details were supplied/confirmed by the user."
            if updated["citation_eligible"]
            else "Full text was uploaded by the user. Bibliographic metadata must be confirmed before ProjectReady may create a new citation from this paper."
        )
    if updated.get("citation_eligible"):
        updated["user_verified"] = True
        updated["apa_hint"] = _apa_hint(updated)
    else:
        updated.pop("user_verified", None)
        updated.pop("apa_hint", None)
    return updated


def prompt_selected_papers(profile: dict[str, Any], chapter_number: int, *, limit: int = 16) -> dict[str, Any]:
    papers = profile.get("selected_papers") or []
    if not isinstance(papers, list) or not papers:
        return {"count": 0, "citation_ready": 0, "papers": []}

    query_parts = [
        _clean(profile.get("title")), _clean(profile.get("research_area")), _clean(profile.get("study_context")),
    ]
    objectives = profile.get("objectives") or []
    if isinstance(objectives, list):
        query_parts.extend(_clean(item) for item in objectives[:4])
    variables = profile.get("variables") or {}
    if isinstance(variables, dict):
        raw = variables.get("raw_variables") or variables.get("constructs") or []
        if isinstance(raw, list):
            query_parts.extend(_clean(item) for item in raw[:8])
        else:
            query_parts.append(_clean(raw))
    chapter_terms = {
        1: "background problem context significance",
        2: "literature theory conceptual empirical gap framework",
        3: "method methodology measurement sampling instrument validity reliability",
        4: "results findings discussion interpretation",
        5: "conclusion implication recommendation",
    }.get(int(chapter_number or 0), "")
    query_parts.append(chapter_terms)
    query_tokens = {tok for tok in re.findall(r"[a-z0-9]{4,}", " ".join(query_parts).lower())}

    ranked: list[tuple[float, dict[str, Any]]] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        haystack = (" ".join([
            _clean(paper.get("title")),
            str(paper.get("evidence_excerpt") or "")[:12000],
        ])).lower()
        tokens = set(re.findall(r"[a-z0-9]{4,}", haystack))
        overlap = len(query_tokens & tokens)
        score = float(overlap)
        if paper.get("citation_eligible"):
            score += 3.0
        if paper.get("metadata_verified"):
            score += 1.5
        ranked.append((score, paper))
    ranked.sort(key=lambda pair: pair[0], reverse=True)

    compact: list[dict[str, Any]] = []
    for _score, paper in ranked[: max(1, min(limit, 20))]:
        compact.append({
            "selected_paper_id": paper.get("id"),
            "filename": paper.get("filename"),
            "title": paper.get("title"),
            "authors": paper.get("authors") or [],
            "year": paper.get("year"),
            "source": paper.get("source"),
            "doi": paper.get("doi"),
            "url": paper.get("url"),
            "metadata_status": paper.get("metadata_status"),
            "citation_eligible": bool(paper.get("citation_eligible")),
            "provenance_note": paper.get("provenance_note"),
            "evidence_excerpt": str(paper.get("evidence_excerpt") or "")[:3600],
        })
    return {
        "count": len(papers),
        "citation_ready": sum(1 for paper in papers if isinstance(paper, dict) and paper.get("citation_eligible")),
        "needs_metadata_confirmation": sum(1 for paper in papers if isinstance(paper, dict) and not paper.get("citation_eligible")),
        "papers_in_prompt": len(compact),
        "papers": compact,
        "rules": [
            "The user deliberately selected and uploaded these papers. Prioritise them when they are directly relevant, while still using ProjectReady-discovered literature where useful.",
            "Use the evidence excerpt only for claims actually supported by the uploaded text. Do not infer results, statistics, quotations or methods that are not visible in the excerpt.",
            "A paper with citation_eligible=true may be cited using its supplied metadata. A paper with citation_eligible=false may inform understanding, but do not create an author-year citation or reference entry from it until the user confirms the bibliographic metadata.",
            "If a non-citation-ready paper is essential to a claim, insert [confirm citation metadata for uploaded paper: filename] rather than inventing author/year details.",
            "Never assume that a user-selected paper supports a claim merely because it was uploaded. Apply the same claim-support and relevance checks used for automatically discovered sources.",
        ],
    }


def public_source_bank(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Strip stored paper excerpts from API responses while preserving citation metadata."""
    output: list[dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        item.pop("evidence_excerpt", None)
        output.append(item)
    return output
