from __future__ import annotations

import hashlib
import re
from typing import Any

from app.citation_matrix import (
    PARAGRAPH_MIN_VERIFIED_SOURCES,
    PARAGRAPH_PREFERRED_VERIFIED_SOURCES,
    _heading_is_citation_light,
    _paragraph_blocks,
    _paragraph_requires_external_evidence,
    allowed_citation_fingerprints,
    citation_fingerprints,
    paragraph_citation_audit,
)

_PLACEHOLDER_RE = re.compile(
    r"\s*\[(?:insert|provide|confirm)\s+(?:a\s+)?(?:verified\s+)?(?:source|citation|reference)[^\]]*\]",
    flags=re.I,
)

_CITATION_RE = re.compile(
    r"(?:\([^()]*?(?:19|20)\d{2}[a-z]?[^()]*\)|\b[A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?\s*\((?:19|20)\d{2}[a-z]?\)|(?<!\w)\[(?:\d+\s*(?:[-,;]\s*\d+)*)\])",
    flags=re.I,
)

_PROJECT_SPECIFIC_PREFIXES = (
    "this study ", "the present study ", "the current study ", "in this study ",
    "the study will ", "the study used ", "the study employed ", "the study examined ",
    "the first hypothesis ", "the second hypothesis ", "the third hypothesis ",
    "the fourth hypothesis ", "the fifth hypothesis ", "the sixth hypothesis ",
    "the seventh hypothesis ", "the eighth hypothesis ",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _claim_id(workflow: str, chapter_number: int, heading: str, paragraph_index: int, sentence_index: int, text: str) -> str:
    raw = f"{workflow}|{chapter_number}|{heading}|{paragraph_index}|{sentence_index}|{_clean(text).lower()}"
    return "claim_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _paragraph_gap_id(workflow: str, chapter_number: int, heading: str, paragraph_index: int, text: str) -> str:
    raw = f"{workflow}|{chapter_number}|{heading}|{paragraph_index}|{_clean(text).lower()}"
    return "para_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _sentences(paragraph: str) -> list[str]:
    value = str(paragraph or "").strip()
    if not value:
        return []
    # Academic prose splitter that avoids breaking most author initials/abbreviations.
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[A-Z\[]|\d))", value)
    return [part.strip() for part in parts if part.strip()]




def _claim_paragraph_is_evidence_led(paragraph: str, heading: str, chapter_number: int) -> bool:
    value = _clean(paragraph)
    if not value or _heading_is_citation_light(heading, chapter_number):
        return False
    words = re.findall(r"\b[\w’'-]+\b", value)
    if len(words) < 12:
        return False
    if value.startswith("[ACTION REQUIRED") or value.startswith("[CONFIRM") or value.startswith("[PROVIDE"):
        return False
    if int(chapter_number or 0) == 4 and "discussion" not in _clean(heading).lower():
        return False
    return True


def _sentence_needs_source(sentence: str, chapter_number: int) -> bool:
    value = _clean(sentence)
    if not value:
        return False
    if _CITATION_RE.search(value):
        return False
    if value.startswith("[") and value.endswith("]"):
        return False
    words = re.findall(r"\b[\w’'-]+\b", value)
    if len(words) < 12:
        return False
    lowered = value.lower()
    if any(lowered.startswith(prefix) for prefix in _PROJECT_SPECIFIC_PREFIXES):
        broader_markers = ("research shows", "evidence", "studies", "literature", "has been", "have been", "%", "percent")
        if not any(marker in lowered for marker in broader_markers):
            return False
    # Chapter-roadmap and internal navigation sentences are not external claims.
    roadmap_prefixes = (
        "this chapter presents", "this chapter outlines", "this chapter introduces",
        "the chapter presents", "the chapter outlines", "the chapter introduces",
        "this section presents", "this section introduces", "the present section",
        "the next section", "the following section", "subsequent sections",
    )
    if lowered.startswith(roadmap_prefixes):
        return False
    if re.match(r"^(?:h\d+[a-z]?|rq\d+|objective\s+\d+)\s*[:.]", lowered):
        return False
    if int(chapter_number or 0) == 4 and not any(token in lowered for token in ("consistent with", "contrasts with", "supports", "previous studies", "literature", "research")):
        return False
    # Explicit source placeholders always require review. Otherwise flag only
    # sentences that visibly make an empirical, factual or relationship claim.
    if _PLACEHOLDER_RE.search(value):
        return True
    evidence_markers = (
        "research ", "researchers ", "evidence ", "studies ", "study found", "study reported",
        "literature ", "meta-analysis", "systematic review", "reported that", "found that",
        "showed that", "demonstrated that", "identified that", "indicated that", "suggested that",
        "has been associated", "have been associated", "is associated", "are associated",
        "relationship between", "linked to", "predicts ", "predict ", "influences ", "influence ",
        "affects ", "affect ", "leads to", "resulted in", "results in", "statistically significant",
        "prevalence", "incidence", "percentage", " percent", "%", "increased", "decreased",
    )
    return any(marker in lowered for marker in evidence_markers)


def remove_review_item_placeholder(text: str, item: dict[str, Any]) -> tuple[str, bool]:
    """Remove only the source-needed placeholder attached to a reviewed item.

    Approval or Ignore should never leave a stale '[insert verified source ...]'
    marker in the student's chapter. The claim text itself is preserved.
    """
    value = str(text or "")
    original_sentence = str(item.get("original_sentence") or "")
    if original_sentence and original_sentence in value:
        cleaned = _PLACEHOLDER_RE.sub("", original_sentence).strip()
        return value.replace(original_sentence, cleaned, 1), cleaned != original_sentence
    paragraph_text = str(item.get("paragraph_text") or "")
    if paragraph_text and paragraph_text in value:
        cleaned = _PLACEHOLDER_RE.sub("", paragraph_text).strip()
        return value.replace(paragraph_text, cleaned, 1), cleaned != paragraph_text
    return value, False

def build_claim_support_review(
    text: str,
    profile: dict[str, Any],
    *,
    chapter_number: int,
    workflow: str = "draft",
    original_text: str = "",
) -> dict[str, Any]:
    allowed, structured = allowed_citation_fingerprints(profile, original_text=original_text)
    claims: list[dict[str, Any]] = []
    claim_ids: set[str] = set()
    evidence_paragraphs = 0
    paragraph_records: dict[int, dict[str, Any]] = {}

    for paragraph_index, (heading, paragraph) in enumerate(_paragraph_blocks(text), start=1):
        if not _claim_paragraph_is_evidence_led(paragraph, heading, chapter_number):
            continue
        evidence_paragraphs += 1
        paragraph_records[paragraph_index] = {"heading": heading, "text": paragraph}
        paragraph_used = citation_fingerprints(paragraph)
        paragraph_verified = paragraph_used & allowed
        explicit_placeholder_present = bool(_PLACEHOLDER_RE.search(paragraph))
        # When a paragraph already satisfies the verified 2-source minimum, do
        # not manufacture sentence-level review work unless the draft itself
        # contains an explicit source-needed placeholder.
        if len(paragraph_verified) >= PARAGRAPH_MIN_VERIFIED_SOURCES and not explicit_placeholder_present:
            continue
        paragraph_claims_added = 0
        for sentence_index, sentence in enumerate(_sentences(paragraph), start=1):
            if not _sentence_needs_source(sentence, chapter_number):
                continue
            if paragraph_claims_added >= 3:
                break
            clean_claim = _PLACEHOLDER_RE.sub("", sentence).strip()
            if not clean_claim:
                continue
            item_id = _claim_id(workflow, chapter_number, heading, paragraph_index, sentence_index, clean_claim)
            if item_id in claim_ids:
                continue
            claim_ids.add(item_id)
            claims.append({
                "id": item_id,
                "type": "claim",
                "status": "needs_source",
                "heading": heading,
                "paragraph_index": paragraph_index,
                "sentence_index": sentence_index,
                "claim_text": clean_claim,
                "original_sentence": sentence,
                "search_query": clean_claim[:420],
                "paragraph_verified_sources": len(paragraph_verified),
                "paragraph_minimum_verified_sources": PARAGRAPH_MIN_VERIFIED_SOURCES,
                "paragraph_preferred_verified_sources": PARAGRAPH_PREFERRED_VERIFIED_SOURCES,
                "candidates": [],
                "approved_sources": [],
                "note": "This evidence-bearing claim currently has no in-text citation.",
            })
            paragraph_claims_added += 1

    paragraph_audit = paragraph_citation_audit(
        text,
        profile,
        chapter_number=chapter_number,
        original_text=original_text,
    )
    density_gaps: list[dict[str, Any]] = []
    for item in paragraph_audit.get("under_supported_paragraphs") or []:
        paragraph_index = int(item.get("paragraph_index") or 0)
        record = paragraph_records.get(paragraph_index) or {}
        paragraph_text = _clean(record.get("text") or item.get("excerpt"))
        excerpt = paragraph_text[:420]
        gap_id = _paragraph_gap_id(
            workflow,
            chapter_number,
            _clean(item.get("heading") or record.get("heading")),
            paragraph_index,
            paragraph_text,
        )
        density_gaps.append({
            "id": gap_id,
            "type": "paragraph_density",
            "status": "needs_more_verified_sources",
            "heading": _clean(item.get("heading")),
            "paragraph_index": paragraph_index,
            "paragraph_text": paragraph_text,
            "excerpt": excerpt,
            "verified_sources": int(item.get("verified_sources") or 0),
            "minimum_verified_sources": PARAGRAPH_MIN_VERIFIED_SOURCES,
            "preferred_verified_sources": PARAGRAPH_PREFERRED_VERIFIED_SOURCES,
            "search_query": excerpt[:420],
            "candidates": [],
            "approved_sources": [],
        })

    return {
        "workflow": workflow,
        "chapter_number": int(chapter_number or 0),
        "status": "review_required" if claims or density_gaps else "ready",
        "claim_review_required": bool(claims),
        "citation_density_review_required": bool(density_gaps),
        "unsupported_claim_count": len(claims),
        "under_supported_paragraph_count": len(density_gaps),
        "evidence_paragraph_count": evidence_paragraphs,
        "claims": claims,
        "paragraph_density_gaps": density_gaps,
        "paragraph_citation_audit": paragraph_audit,
        "policy": (
            "Before final export, every evidence-bearing claim without a citation must be reviewed. "
            "Only bibliographically verified sources may be approved, and the student must confirm that the source actually supports the claim. "
            "ProjectReady never invents a citation to satisfy the density target."
        ),
        "verified_source_fingerprint_count": len(structured),
        "final_output_ready": not bool(claims or density_gaps),
    }


def _source_key(source: dict[str, Any]) -> str:
    doi = _clean(source.get("doi")).lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", _clean(source.get("title")).lower())[:120]
    year = _clean(source.get("year"))
    return f"title:{title}:{year}" if title else ""


def public_candidate(source: dict[str, Any]) -> dict[str, Any]:
    abstract = _clean(source.get("evidence_excerpt") or source.get("abstract"))
    return {
        "candidate_id": _source_key(source),
        "title": _clean(source.get("title")),
        "authors": source.get("authors") or [],
        "year": _clean(source.get("year")),
        "journal": _clean(source.get("journal") or source.get("source") or source.get("venue")),
        "doi": _clean(source.get("doi")),
        "url": _clean(source.get("url") or source.get("landing_page_url")),
        "database": _clean(source.get("database")),
        "databases_found": source.get("databases_found") or ([_clean(source.get("database"))] if _clean(source.get("database")) else []),
        "verification_basis": _clean(source.get("verification_basis")),
        "relevance_tier": _clean(source.get("relevance_tier")),
        "relevance_reason": _clean(source.get("relevance_reason")),
        "suggested_use": _clean(source.get("suggested_use")),
        "evidence_excerpt": abstract[:1600],
        "metadata_verified": bool(source.get("metadata_verified", source.get("citation_eligible", False))),
        "citation_eligible": bool(source.get("citation_eligible", False)),
        "claim_support_eligible": bool(source.get("claim_support_eligible", False) and abstract),
        "requires_manual_source_text_confirmation": not bool(source.get("claim_support_eligible", False) and abstract),
    }


def merge_source_into_bank(profile: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    bank = profile.get("source_bank") or []
    if not isinstance(bank, list):
        bank = []
    key = _source_key(source)
    for existing in bank:
        if isinstance(existing, dict) and _source_key(existing) == key and key:
            existing.update({k: v for k, v in source.items() if v not in (None, "", [], {})})
            profile["source_bank"] = bank
            return existing
    bank.append(source)
    profile["source_bank"] = bank[:220]
    return source


def _author_surname(author: str) -> str:
    value = _clean(author)
    if not value:
        return ""
    if "," in value:
        return value.split(",", 1)[0].strip()
    organisation_markers = ("university", "organisation", "organization", "ministry", "agency", "bank", "institute", "association", "commission")
    if any(marker in value.lower() for marker in organisation_markers):
        return value
    parts = value.split()
    return parts[-1] if parts else value


def author_year_token(source: dict[str, Any]) -> str:
    authors = source.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    surnames = [_author_surname(str(author)) for author in authors if _author_surname(str(author))]
    year = _clean(source.get("year")) or "n.d."
    if not surnames:
        title = _clean(source.get("title"))
        lead = title[:50] if title else "Verified source"
    elif len(surnames) == 1:
        lead = surnames[0]
    elif len(surnames) == 2:
        lead = f"{surnames[0]} & {surnames[1]}"
    else:
        lead = f"{surnames[0]} et al."
    return f"{lead}, {year}"


def _citation_group(approved: list[dict[str, Any]]) -> tuple[str, list[str]]:
    tokens: list[str] = []
    seen: set[str] = set()
    for source in approved[:3]:
        token = author_year_token(source)
        if token and token.casefold() not in seen:
            seen.add(token.casefold())
            tokens.append(token)
    return (("(" + "; ".join(tokens) + ")") if tokens else "", tokens)


def _append_citation_to_sentence(sentence: str, citation: str) -> str:
    cleaned = _PLACEHOLDER_RE.sub("", sentence).strip()
    if cleaned.endswith((".", "!", "?")):
        return cleaned[:-1].rstrip() + f" {citation}" + cleaned[-1]
    return cleaned + f" {citation}"


def apply_approved_claim_citations(
    text: str,
    review: dict[str, Any],
    *,
    citation_style: str = "APA 7th",
) -> tuple[str, dict[str, Any]]:
    value = str(text or "")
    applied_claims = 0
    applied_paragraphs = 0
    added_reference_mentions = 0
    used_source_keys: set[str] = set()
    unresolved = 0
    style = _clean(citation_style).lower()
    numeric_style = "vancouver" in style or "ieee" in style

    # Apply paragraph-density approvals first. This lets one defensible 2-3 source
    # group support the paragraph without forcing a citation after every sentence.
    for gap in review.get("paragraph_density_gaps") or []:
        if not isinstance(gap, dict) or gap.get("status") == "ignored":
            continue
        approved = [item for item in gap.get("approved_sources") or [] if isinstance(item, dict)]
        paragraph_text = str(gap.get("paragraph_text") or "")
        target = paragraph_text if paragraph_text in value else _PLACEHOLDER_RE.sub("", paragraph_text).strip()
        if not approved or not target or target not in value:
            continue
        citation, tokens = _citation_group(approved)
        if not citation:
            continue
        if numeric_style:
            gap["status"] = "approved_for_numeric_formatting"
            gap["approved_citation_tokens"] = tokens
            continue
        replacement = _append_citation_to_sentence(target, citation)
        value = value.replace(target, replacement, 1)
        gap["status"] = "resolved"
        gap["applied_citation"] = citation
        applied_paragraphs += 1
        added_reference_mentions += len(tokens)
        for source in approved[:3]:
            key = _source_key(source)
            if key:
                used_source_keys.add(key)

    for claim in review.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("status") == "ignored":
            continue
        approved = [item for item in claim.get("approved_sources") or [] if isinstance(item, dict)]
        original_sentence = str(claim.get("original_sentence") or "")
        target = original_sentence if original_sentence in value else _PLACEHOLDER_RE.sub("", original_sentence).strip()
        if not approved or not target or target not in value:
            if claim.get("status") != "resolved":
                unresolved += 1
            continue
        citation, tokens = _citation_group(approved)
        if not citation:
            unresolved += 1
            continue
        if numeric_style:
            claim["status"] = "approved_for_numeric_formatting"
            claim["approved_citation_tokens"] = tokens
            unresolved += 1
            continue
        # If the paragraph pass already inserted all approved tokens, avoid a
        # duplicate citation group and allow the fresh audit to decide coverage.
        window_start = max(0, value.find(target) - 800)
        window_end = min(len(value), value.find(target) + len(target) + 800)
        nearby = value[window_start:window_end].lower()
        if tokens and all(token.lower() in nearby for token in tokens):
            claim["status"] = "resolved"
            continue
        value = value.replace(target, _append_citation_to_sentence(target, citation), 1)
        claim["status"] = "resolved"
        claim["applied_citation"] = citation
        applied_claims += 1
        added_reference_mentions += len(tokens)
        for source in approved[:3]:
            key = _source_key(source)
            if key:
                used_source_keys.add(key)

    return value, {
        "applied_claim_citation_groups": applied_claims,
        "applied_paragraph_density_citation_groups": applied_paragraphs,
        "citation_groups_added": applied_claims + applied_paragraphs,
        "verified_citation_references_added": added_reference_mentions,
        "unique_verified_sources_added": len(used_source_keys),
        "unresolved_after_apply": unresolved,
        "citation_style": citation_style,
        "note": (
            "Author-date citations are inserted deterministically from student-approved, verified source metadata. "
            "The final approval summary reports both citation groups and individual verified source references added. "
            "IEEE/Vancouver approvals are retained for the final numbering pass so existing numeric citation order is not corrupted."
        ),
    }

def stored_claim_review_status(profile: dict[str, Any], *, workflow: str, chapter_number: int) -> dict[str, Any]:
    store = profile.get("claim_support_reviews") or {}
    if not isinstance(store, dict):
        store = {}
    mode = "strengthener" if str(workflow or "").lower().startswith("strength") else "draft"
    review = store.get(f"{mode}:{int(chapter_number or 0)}")
    if not isinstance(review, dict):
        return {
            "ready": False,
            "reason": "Claim Support Review has not yet been completed for this chapter.",
            "review": None,
        }
    ready = bool(review.get("final_output_ready")) and not bool(
        review.get("unsupported_claim_count") or review.get("under_supported_paragraph_count")
    )
    return {
        "ready": ready,
        "reason": "" if ready else "Resolve the highlighted unsupported claims and paragraph citation-density gaps before final export.",
        "review": review,
    }
