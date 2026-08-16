from __future__ import annotations

import re
from typing import Any

# Citation-density matrix supplied for ProjectReady AI. Values are references
# (individual cited works), not merely citation brackets, per 1,000 substantive words.
CITATION_DENSITY_MATRIX: dict[str, dict[str, tuple[int, int]]] = {
    "stem": {
        "introduction": (5, 10),
        "literature_review": (15, 25),
        "methodology": (2, 5),
        "results_discussion": (8, 15),
        "conclusion": (0, 3),
    },
    "social_sciences": {
        "introduction": (8, 12),
        "literature_review": (20, 35),
        "methodology": (4, 8),
        "results_discussion": (12, 20),
        "conclusion": (2, 5),
    },
    "humanities": {
        "introduction": (10, 15),
        "literature_review": (25, 40),
        "methodology": (1, 3),
        "results_discussion": (15, 25),
        "conclusion": (3, 6),
    },
    "professional_health": {
        "introduction": (8, 15),
        "literature_review": (20, 30),
        "methodology": (5, 10),
        "results_discussion": (10, 18),
        "conclusion": (1, 4),
    },
}



PARAGRAPH_MIN_VERIFIED_SOURCES = 2
PARAGRAPH_PREFERRED_VERIFIED_SOURCES = 3

# The paragraph rule applies only where external evidence is academically appropriate.
# Research-logic lists, the student's own results, project-specific procedures and
# finding-led conclusions should not be padded with citations simply to meet a count.
_CITATION_LIGHT_HEADING_PATTERNS: dict[int, tuple[str, ...]] = {
    1: (
        "purpose of the study", "research objective", "research question",
        "scope of the study", "delimitation", "limitation", "definition of terms",
        "organization of the study", "organisation of the study",
    ),
    3: (
        "data collection procedure", "data collection procedures", "ethical consideration",
        "data processing", "chapter summary",
    ),
    4: (
        "response rate", "respondent profile", "sample profile", "descriptive statistics",
        "results", "hypothesis testing", "objective results", "chapter summary",
    ),
    5: (
        "summary of findings", "conclusion", "recommendation", "future research",
        "chapter summary",
    ),
}

DISCIPLINE_LABELS = {
    "stem": "STEM (Hard Sciences)",
    "social_sciences": "Social Sciences (Qualitative / Quantitative)",
    "humanities": "Humanities (Arts / History)",
    "professional_health": "Professional & Health (Nursing / Business)",
}

_VALID_DISCIPLINE_ALIASES = {
    "stem": "stem", "hard sciences": "stem", "science": "stem",
    "social": "social_sciences", "social sciences": "social_sciences", "social_science": "social_sciences",
    "humanities": "humanities", "arts": "humanities", "history": "humanities",
    "professional": "professional_health", "health": "professional_health",
    "professional_health": "professional_health", "professional & health": "professional_health",
    "business": "professional_health", "nursing": "professional_health",
}

_KEYWORDS: dict[str, set[str]] = {
    "professional_health": {
        "accounting", "banking", "business", "commerce", "finance", "financial", "management",
        "marketing", "procurement", "logistics", "entrepreneurship", "human resource", "hrm",
        "nursing", "medicine", "medical", "clinical", "public health", "health", "pharmacy",
        "midwifery", "allied health", "hospital", "healthcare", "professional",
    },
    "stem": {
        "engineering", "computer science", "computing", "ict", "information technology", "physics",
        "chemistry", "biology", "mathematics", "statistics", "biochemistry", "microbiology",
        "environmental science", "agriculture", "geology", "laboratory", "software", "data science",
    },
    "humanities": {
        "history", "historical", "literature", "english", "languages", "linguistics", "philosophy",
        "religion", "religious studies", "theology", "arts", "music", "theatre", "archaeology",
        "classics", "cultural studies",
    },
    "social_sciences": {
        "education", "educational", "economics", "sociology", "psychology", "political science",
        "public administration", "public policy", "governance", "development studies", "social work",
        "communication", "geography", "criminology", "international relations", "anthropology",
        "teacher", "students", "school", "higher education",
    },
}

_CHAPTER_MATRIX_SECTION = {
    1: "introduction",
    2: "literature_review",
    3: "methodology",
    4: "results_discussion",
    5: "conclusion",
}

# Thesis-specific exceptions. The supplied matrix remains the base standard, but
# sections that conventionally report the student's own research logic/results
# should not be padded with citations merely to hit a numerical target.
_CITATION_LIGHT_SECTION_IDS = {
    "ch1_purpose", "ch1_objectives", "ch1_questions", "ch1_structure",
    "ch4_intro", "ch4_response_rate", "ch4_profile", "ch4_descriptive", "ch4_objective_results",
    "ch4_uploaded_results", "ch4_results_objectives",
    "ch5_intro", "ch5_summary_study", "ch5_summary_findings", "ch5_recommendations", "ch5_future",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def infer_citation_discipline(profile: dict[str, Any]) -> dict[str, str]:
    requested = _clean(
        profile.get("citation_discipline_matrix")
        or profile.get("citation_matrix_discipline")
        or profile.get("discipline_category")
    ).lower()
    if requested and requested not in {"auto", "automatic", "auto-detect", "autodetect"}:
        key = _VALID_DISCIPLINE_ALIASES.get(requested.replace("-", " "), requested.replace("-", "_"))
        if key in CITATION_DENSITY_MATRIX:
            return {
                "key": key,
                "label": DISCIPLINE_LABELS[key],
                "basis": "selected by user",
            }

    haystack = " ".join(
        _clean(profile.get(field)).lower()
        for field in ("discipline", "programme", "department", "research_area", "title", "study_context")
        if _clean(profile.get(field))
    )
    scores: dict[str, int] = {key: 0 for key in CITATION_DENSITY_MATRIX}
    matched: dict[str, list[str]] = {key: [] for key in CITATION_DENSITY_MATRIX}
    for key, words in _KEYWORDS.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", haystack):
                scores[key] += 2 if " " in word else 1
                matched[key].append(word)
    best = max(scores, key=scores.get) if scores else "social_sciences"
    if scores.get(best, 0) <= 0:
        best = "social_sciences"
        basis = "automatic default because the discipline could not be identified confidently"
    else:
        basis = "auto-detected from " + ", ".join(matched[best][:4])
    return {"key": best, "label": DISCIPLINE_LABELS[best], "basis": basis}


def chapter_matrix_section(chapter_number: int, chapter_type: str = "") -> str:
    try:
        number = int(chapter_number or 0)
    except Exception:
        number = 0
    if number in _CHAPTER_MATRIX_SECTION:
        return _CHAPTER_MATRIX_SECTION[number]
    value = _clean(chapter_type).lower()
    if "literature" in value:
        return "literature_review"
    if "method" in value:
        return "methodology"
    if "result" in value or "discussion" in value:
        return "results_discussion"
    if "conclusion" in value or "recommend" in value or "summary" in value:
        return "conclusion"
    return "introduction"


def citation_target(
    profile: dict[str, Any],
    chapter_number: int,
    *,
    chapter_type: str = "",
    section_id: str = "",
) -> dict[str, Any]:
    discipline = infer_citation_discipline(profile)
    matrix_section = chapter_matrix_section(chapter_number, chapter_type)
    minimum, maximum = CITATION_DENSITY_MATRIX[discipline["key"]][matrix_section]
    preferred = int(round((minimum + maximum) / 2))
    exception = ""

    sid = _clean(section_id)
    if sid in _CITATION_LIGHT_SECTION_IDS:
        if sid.startswith("ch4_"):
            minimum, preferred, maximum = 0, 1, 3
            exception = "Results-only section: report the study's own results without citation padding; reserve the matrix range for discussion."
        elif sid.startswith("ch1_"):
            minimum, preferred, maximum = 0, 0, 2
            exception = "Research-logic or organisational section: citations are normally unnecessary unless a specific claim requires evidence."
        elif sid.startswith("ch5_"):
            minimum, preferred, maximum = 0, 1, min(3, maximum)
            exception = "Finding-led summary/recommendation section: cite only where external evidence is genuinely needed."

    return {
        "discipline_key": discipline["key"],
        "discipline_label": discipline["label"],
        "discipline_basis": discipline["basis"],
        "matrix_section": matrix_section,
        "minimum": int(minimum),
        "preferred": int(preferred),
        "maximum": int(maximum),
        "unit": "verified referenced works per 1,000 substantive words",
        "section_exception": exception,
    }


def build_section_citation_plan(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str] | None,
    section_word_budgets: dict[str, dict[str, int]] | None = None,
    *,
    chapter_type: str = "",
) -> dict[str, Any]:
    base = citation_target(profile, chapter_number, chapter_type=chapter_type)
    section_word_budgets = section_word_budgets or {}
    sections: list[dict[str, Any]] = []
    total_words = 0
    weighted_min = weighted_preferred = weighted_max = 0.0
    for sid in [str(x) for x in (selected_section_ids or []) if str(x).strip()]:
        target = citation_target(profile, chapter_number, chapter_type=chapter_type, section_id=sid)
        words = int((section_word_budgets.get(sid) or {}).get("target_words") or 1000)
        total_words += words
        weighted_min += target["minimum"] * words
        weighted_preferred += target["preferred"] * words
        weighted_max += target["maximum"] * words
        sections.append({"section_id": sid, "target_words": words, **target})

    if total_words:
        weighted = {
            "minimum": round(weighted_min / total_words, 1),
            "preferred": round(weighted_preferred / total_words, 1),
            "maximum": round(weighted_max / total_words, 1),
        }
    else:
        weighted = {k: base[k] for k in ("minimum", "preferred", "maximum")}

    return {
        "discipline_key": base["discipline_key"],
        "discipline_label": base["discipline_label"],
        "discipline_basis": base["discipline_basis"],
        "matrix_section": base["matrix_section"],
        "matrix_target": {k: base[k] for k in ("minimum", "preferred", "maximum")},
        "weighted_selected_section_target": weighted,
        "unit": base["unit"],
        "sections": sections,
        "rules": [
            "Treat the matrix as an evidence-density guide, never as a quota.",
            "Count individual referenced works, so a parenthetical citation containing three different works counts as three references.",
            "Only verified or user-supplied sources may count toward the target.",
            "Never invent an author, year, DOI, title, journal, volume, issue, page range, URL, quotation or finding to reach the target.",
            "If verified evidence is insufficient, remain below the target and use a precise [insert verified source for this claim] placeholder where evidence is required.",
            "Pure results, objectives, research questions and other research-logic sections remain citation-light even when the surrounding chapter has a higher matrix target.",
        ],
    }


def _body_only(text: str) -> str:
    value = str(text or "")
    match = re.search(r"(?im)^#{0,4}\s*references\s*$", value)
    return value[: match.start()] if match else value


def _normalise_author_token(value: str) -> str:
    value = re.sub(r"\bet\s+al\.?\b", "", value, flags=re.I)
    value = re.sub(r"[^A-Za-z0-9&'’-]+", " ", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def _fingerprints_from_citation_chunk(chunk: str) -> set[str]:
    years = re.findall(r"\b((?:19|20)\d{2}[a-z]?)\b", chunk, flags=re.I)
    if not years:
        return set()
    author_part = re.split(r",?\s*(?:19|20)\d{2}[a-z]?", chunk, maxsplit=1, flags=re.I)[0]
    author = _normalise_author_token(author_part)
    if not author:
        return set()
    # The final surname/token is stable across full-name and abbreviated metadata.
    tokens = [x for x in re.split(r"\s+|\s*&\s*|\s+and\s+", author) if x and x not in {"and"}]
    lead = tokens[0] if tokens else author
    return {f"{lead}:{year.lower()}" for year in years}


def citation_fingerprints(text: str) -> set[str]:
    body = _body_only(text)
    keys: set[str] = set()
    for group in re.findall(r"\(([^()]*?(?:19|20)\d{2}[a-z]?[^()]*)\)", body, flags=re.I):
        for chunk in re.split(r"\s*;\s*", group):
            keys.update(_fingerprints_from_citation_chunk(chunk))
    for author, year in re.findall(
        r"\b([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?)\s*\(((?:19|20)\d{2}[a-z]?)\)",
        body,
    ):
        keys.update(_fingerprints_from_citation_chunk(f"{author}, {year}"))
    return keys


def _structured_sources(profile: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in ("source_bank", "attached_sources"):
        items = profile.get(field) or []
        if isinstance(items, list):
            out.extend(x for x in items if isinstance(x, dict))
    retrieved = profile.get("retrieved_sources") or {}
    if isinstance(retrieved, dict):
        items = retrieved.get("sources") or []
        if isinstance(items, list):
            out.extend(x for x in items if isinstance(x, dict))
    deduped: list[dict[str, Any]] = []
    for src in out:
        if src.get("citation_eligible") is False:
            continue
        key = _clean(src.get("doi")).lower() or re.sub(r"[^a-z0-9]+", "", _clean(src.get("title")).lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(src)
    return deduped


def _source_fingerprints(source: dict[str, Any]) -> set[str]:
    year = _clean(source.get("year"))
    if not re.fullmatch(r"(?:19|20)\d{2}[a-z]?", year, flags=re.I):
        return set()
    authors = source.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    if not authors:
        return set()
    first = _clean(authors[0])
    # Metadata often uses full names. Use surname as the citation lead for people,
    # but keep the first meaningful token as an alternate for institutional authors.
    parts = [p for p in re.split(r"\s+", re.sub(r"[,]+", " ", first)) if p]
    candidates = set()
    if parts:
        candidates.add(parts[-1])
        candidates.add(parts[0])
    return {f"{_normalise_author_token(name)}:{year.lower()}" for name in candidates if _normalise_author_token(name)}


def allowed_citation_fingerprints(profile: dict[str, Any], *, original_text: str = "") -> tuple[set[str], set[str]]:
    structured: set[str] = set()
    for source in _structured_sources(profile):
        structured.update(_source_fingerprints(source))
    supplied: set[str] = set(structured)
    raw_parts = [
        original_text,
        _clean(profile.get("citation_evidence_notes")),
        _clean(profile.get("evidence_anchors")),
        _clean((profile.get("student_contribution") or {}).get("evidence_anchors") if isinstance(profile.get("student_contribution"), dict) else ""),
    ]
    previous = profile.get("previous_chapters_context") or {}
    if isinstance(previous, dict):
        raw_parts.extend(_clean(item.get("text")) for item in previous.get("items") or [] if isinstance(item, dict))
    elif isinstance(previous, str):
        raw_parts.append(previous)
    for raw in raw_parts:
        supplied.update(citation_fingerprints(raw))
    return supplied, structured


def reference_mention_count(text: str) -> int:
    """Estimate individual cited works in the chapter body.

    A group such as (A, 2024; B, 2025; C, 2026) counts as three referenced works.
    This is intentionally distinct from counting one citation bracket/event.
    """
    body = _body_only(text)
    count = 0
    occupied: list[tuple[int, int]] = []
    for match in re.finditer(r"\(([^()]*?(?:19|20)\d{2}[a-z]?[^()]*)\)", body, flags=re.I):
        group = match.group(1)
        if re.fullmatch(r"\s*(?:19|20)\d{2}[a-z]?\s*", group, flags=re.I):
            continue
        mentions = 0
        for chunk in re.split(r"\s*;\s*", group):
            years = re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", chunk, flags=re.I)
            if years and re.search(r"[A-Za-z]", chunk):
                mentions += max(1, len(years))
        if mentions:
            count += mentions
            occupied.append(match.span())
    # Narrative forms such as Smith (2024) were intentionally skipped above.
    for match in re.finditer(r"\b[A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?\s*\((?:19|20)\d{2}[a-z]?\)", body):
        if not any(start <= match.start() < end for start, end in occupied):
            count += 1
    for match in re.finditer(r"(?<!\w)\[((?:\d+\s*(?:[-,;]\s*\d+)*\s*))\]", body):
        nums = re.findall(r"\d+", match.group(1))
        count += len(nums)
    return count


def citation_density_metrics(text: str, target: dict[str, Any] | None = None, *, verified_count: int | None = None) -> dict[str, Any]:
    body = _body_only(text)
    words = len(re.findall(r"\b[\w’'-]+\b", re.sub(r"[#|*_`$<>]", " ", body)))
    mentions = reference_mention_count(body)
    verified = mentions if verified_count is None else max(0, int(verified_count))
    density = round(mentions * 1000 / words, 1) if words else 0.0
    verified_density = round(verified * 1000 / words, 1) if words else 0.0
    result = {
        "word_count": words,
        "reference_mentions": mentions,
        "references_per_1000_words": density,
        "verified_reference_mentions": verified,
        "verified_references_per_1000_words": verified_density,
    }
    if target:
        minimum = float(target.get("minimum") or 0)
        maximum = float(target.get("maximum") or 0)
        if verified_density < minimum:
            status = "under_target"
        elif maximum and verified_density > maximum:
            status = "above_matrix_range"
        else:
            status = "within_range"
        result.update({
            "target_minimum": minimum,
            "target_preferred": float(target.get("preferred") or 0),
            "target_maximum": maximum,
            "status": status,
        })
    return result


def _heading_is_citation_light(heading: str, chapter_number: int) -> bool:
    value = _clean(heading).lower()
    if not value:
        return False
    patterns = _CITATION_LIGHT_HEADING_PATTERNS.get(int(chapter_number or 0), ())
    if int(chapter_number or 0) == 4 and "discussion" in value:
        return False
    return any(pattern in value for pattern in patterns)


def _paragraph_blocks(text: str) -> list[tuple[str, str]]:
    """Return (current heading, paragraph) pairs from Markdown-like chapter text."""
    body = _body_only(text)
    heading = ""
    paragraphs: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if buffer:
            paragraph = " ".join(line.strip() for line in buffer if line.strip()).strip()
            if paragraph:
                paragraphs.append((heading, paragraph))
            buffer = []

    for raw in body.splitlines():
        line = raw.strip()
        heading_match = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading_match:
            flush()
            heading = heading_match.group(1).strip()
            continue
        if not line:
            flush()
            continue
        if line.startswith("|") or line.startswith("```") or line.startswith("$$"):
            flush()
            continue
        buffer.append(line)
    flush()
    return paragraphs


def _paragraph_requires_external_evidence(paragraph: str, heading: str, chapter_number: int) -> bool:
    value = _clean(paragraph)
    if not value:
        return False
    if _heading_is_citation_light(heading, chapter_number):
        return False
    words = re.findall(r"\b[\w’'-]+\b", value)
    if len(words) < 55:
        return False
    if re.match(r"^(?:H\d+[a-z]?|RQ\d+|Objective\s+\d+)\s*:\s*", value, flags=re.I):
        return False
    if value.startswith("[ACTION REQUIRED") or value.startswith("[CONFIRM") or value.startswith("[PROVIDE"):
        return False
    if re.match(r"^\d+[.)]\s+", value) and len(words) < 90:
        return False
    # Chapter Four result reporting should stay citation-light unless the heading is explicitly discussion-oriented.
    if int(chapter_number or 0) == 4 and "discussion" not in _clean(heading).lower():
        return False
    return True


def paragraph_citation_audit(
    text: str,
    profile: dict[str, Any],
    *,
    chapter_number: int = 0,
    original_text: str = "",
    minimum_sources: int = PARAGRAPH_MIN_VERIFIED_SOURCES,
    preferred_sources: int = PARAGRAPH_PREFERRED_VERIFIED_SOURCES,
) -> dict[str, Any]:
    """Audit verified source coverage at paragraph level.

    The metric counts distinct allowed author-year source fingerprints in each
    substantive evidence-led paragraph. It never treats an unverified generated
    citation as satisfying the 2-3 source rule.
    """
    allowed, structured = allowed_citation_fingerprints(profile, original_text=original_text)
    eligible = 0
    meeting_minimum = 0
    meeting_preferred = 0
    under_supported: list[dict[str, Any]] = []
    total_verified_links = 0

    for index, (heading, paragraph) in enumerate(_paragraph_blocks(text), start=1):
        if not _paragraph_requires_external_evidence(paragraph, heading, chapter_number):
            continue
        eligible += 1
        used = citation_fingerprints(paragraph)
        verified = used & allowed
        structured_verified = verified & structured
        count = len(verified)
        total_verified_links += count
        if count >= int(minimum_sources):
            meeting_minimum += 1
        if count >= int(preferred_sources):
            meeting_preferred += 1
        if count < int(minimum_sources):
            under_supported.append({
                "paragraph_index": index,
                "heading": heading,
                "verified_sources": count,
                "verified_structured_sources": len(structured_verified),
                "minimum_required_when_evidence_is_available": int(minimum_sources),
                "excerpt": value[:260] if (value := _clean(paragraph)) else "",
            })

    coverage = round(meeting_minimum * 100 / eligible, 1) if eligible else 100.0
    preferred_coverage = round(meeting_preferred * 100 / eligible, 1) if eligible else 100.0
    return {
        "policy": (
            f"Each substantive evidence-led paragraph should normally contain at least {int(minimum_sources)} "
            f"and preferably {int(preferred_sources)} distinct verified sources. If fewer suitable verified sources exist, "
            "ProjectReady must remain below target rather than invent or force a citation."
        ),
        "minimum_verified_sources_per_evidence_paragraph": int(minimum_sources),
        "preferred_verified_sources_per_evidence_paragraph": int(preferred_sources),
        "eligible_evidence_paragraphs": eligible,
        "paragraphs_meeting_minimum": meeting_minimum,
        "paragraphs_meeting_preferred": meeting_preferred,
        "minimum_coverage_percent": coverage,
        "preferred_coverage_percent": preferred_coverage,
        "verified_source_links_across_evidence_paragraphs": total_verified_links,
        "under_supported_paragraph_count": len(under_supported),
        "under_supported_paragraphs": under_supported[:40],
        "passed": len(under_supported) == 0,
        "important_exception": (
            "The rule does not require citation padding in research objectives/questions, project-specific procedures, "
            "the student's own results, or finding-led conclusions/recommendations."
        ),
    }


def citation_provenance_audit(text: str, profile: dict[str, Any], *, original_text: str = "") -> dict[str, Any]:
    used = citation_fingerprints(text)
    allowed, structured = allowed_citation_fingerprints(profile, original_text=original_text)
    unverified = sorted(used - allowed)
    structured_used = used & structured
    supplied_used = (used & allowed) - structured
    return {
        "detected_author_year_sources": len(used),
        "verified_structured_sources": len(structured_used),
        "user_supplied_existing_sources": len(supplied_used),
        "unverified_source_count": len(unverified),
        "unverified_source_keys": unverified[:30],
        "passed": len(unverified) == 0,
        "policy": "No generated citation may remain unless it maps to a verified source record or a citation already supplied by the user.",
    }



def _source_reference_entry(source: dict[str, Any]) -> str:
    """Build a reference entry only from metadata already present in a verified source record."""
    hint = _clean(source.get("reference_entry_hint") or source.get("apa_hint"))
    if hint:
        return hint
    authors = source.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    author_text = ", ".join(_clean(author) for author in authors if _clean(author))
    year = _clean(source.get("year"))
    title = _clean(source.get("title"))
    venue = _clean(source.get("journal") or source.get("source") or source.get("venue") or source.get("publisher"))
    doi = _clean(source.get("doi"))
    locator = _clean(source.get("url") or source.get("landing_page_url"))
    parts: list[str] = []
    if author_text:
        parts.append(author_text.rstrip("."))
    if year:
        parts.append(f"({year}).")
    if title:
        parts.append(title.rstrip(".") + ".")
    if venue:
        parts.append(venue.rstrip(".") + ".")
    if doi:
        clean_doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        parts.append(f"https://doi.org/{clean_doi}")
    elif locator:
        parts.append(locator)
    return " ".join(parts).strip()


def _user_reference_section_entries(raw: str) -> list[str]:
    """Extract reference entries only from a reference list the user actually supplied."""
    text = str(raw or "")
    match = re.search(r"(?im)^#{0,4}\s*(?:\d+(?:\.\d+)*\s+)?(?:references|reference list)\s*$", text)
    if not match:
        return []
    tail = text[match.end():].strip()
    if not tail:
        return []
    appendix = re.search(r"(?im)^#{0,4}\s*(?:appendix|appendices)\b.*$", tail)
    if appendix:
        tail = tail[:appendix.start()].strip()
    blocks = [re.sub(r"\s+", " ", block).strip(" -*•\t") for block in re.split(r"\n\s*\n", tail) if block.strip()]
    if len(blocks) <= 1:
        blocks = [re.sub(r"\s+", " ", line).strip(" -*•\t") for line in tail.splitlines() if line.strip()]
    return [entry for entry in blocks if len(entry) >= 8]


def enforce_verified_reference_list(text: str, profile: dict[str, Any], *, original_text: str = "") -> tuple[str, dict[str, Any]]:
    """Replace model-created reference entries with verified metadata and user-supplied entries.

    This deliberately fails closed. ProjectReady may format metadata it has actually
    retrieved, but it must not retain a plausible-looking reference invented by a model.
    """
    value = str(text or "").strip()
    used = citation_fingerprints(value)
    structured_entries: list[str] = []
    seen_entries: set[str] = set()
    matched_structured_keys: set[str] = set()
    for source in _structured_sources(profile):
        fps = _source_fingerprints(source)
        if not fps or not (fps & used):
            continue
        entry = _source_reference_entry(source)
        if not entry:
            continue
        key = re.sub(r"\W+", "", entry.lower())[:220]
        if key and key not in seen_entries:
            seen_entries.add(key)
            structured_entries.append(entry)
            matched_structured_keys.update(fps & used)

    user_entries: list[str] = []
    user_inputs = [
        original_text,
        _clean(profile.get("citation_evidence_notes")),
        _clean(profile.get("evidence_anchors")),
    ]
    for raw in user_inputs:
        for entry in _user_reference_section_entries(raw):
            key = re.sub(r"\W+", "", entry.lower())[:220]
            if key and key not in seen_entries:
                seen_entries.add(key)
                user_entries.append(entry)

    entries = structured_entries + user_entries
    ref_heading = re.search(r"(?im)^#{0,4}\s*(?:\d+(?:\.\d+)*\s+)?(?:references|reference list)\s*$", value)
    if ref_heading:
        body = value[:ref_heading.start()].rstrip()
        after = value[ref_heading.end():]
        appendix = re.search(r"(?im)^#{0,4}\s*(?:appendix|appendices)\b.*$", after)
        tail = after[appendix.start():].strip() if appendix else ""
    else:
        body = value.rstrip()
        tail = ""

    if used and not entries:
        entries = ["[Complete verified reference details required for the cited user-supplied source(s).]"]
    if entries or ref_heading:
        refs = "# References\n\n" + "\n\n".join(entries or ["[No verified reference entry is available. Add or verify the source before submission.]"])
        value = body + "\n\n" + refs
        if tail:
            value += "\n\n" + tail

    unmatched_used = sorted(used - matched_structured_keys)
    return value.strip(), {
        "verified_reference_entries": len(structured_entries),
        "preserved_user_reference_entries": len(user_entries),
        "used_citation_keys_without_structured_metadata": unmatched_used[:30],
        "reference_list_policy": "Model-created references are discarded. The final list is rebuilt only from retrieved source metadata and reference entries supplied by the user.",
    }

def remove_unverified_generated_citations(text: str, profile: dict[str, Any], *, original_text: str = "") -> tuple[str, dict[str, Any]]:
    """Fail closed on author-year citations that were not supplied or verified.

    The function removes only citation forms that can be matched confidently. It
    never manufactures replacement bibliographic details. Unknown citations are
    replaced with an explicit verification placeholder.
    """
    value = str(text or "")
    allowed, _structured = allowed_citation_fingerprints(profile, original_text=original_text)
    if not allowed:
        # With no evidence bank, every generated author-year citation is suspect.
        allowed = citation_fingerprints(original_text)

    reference_match = re.search(r"(?im)^#{0,4}\s*references\s*$", value)
    body = value[: reference_match.start()] if reference_match else value
    refs = value[reference_match.start():] if reference_match else ""
    removed: list[str] = []

    def parenthetical_repl(match: re.Match[str]) -> str:
        group = match.group(1)
        if re.fullmatch(r"\s*(?:19|20)\d{2}[a-z]?\s*", group, flags=re.I):
            return match.group(0)
        chunks = re.split(r"\s*;\s*", group)
        kept: list[str] = []
        had_citation = False
        for chunk in chunks:
            fps = _fingerprints_from_citation_chunk(chunk)
            if not fps:
                kept.append(chunk)
                continue
            had_citation = True
            if fps.issubset(allowed):
                kept.append(chunk)
            else:
                removed.append(chunk.strip())
        if not had_citation:
            return match.group(0)
        if kept:
            cleaned = "; ".join(x for x in kept if x.strip())
            return f"({cleaned}) [insert verified source for the unsupported citation removed here]"
        return "[insert verified source for this claim]"

    body = re.sub(r"\(([^()]*?(?:19|20)\d{2}[a-z]?[^()]*)\)", parenthetical_repl, body, flags=re.I)

    def narrative_repl(match: re.Match[str]) -> str:
        author, year = match.group(1), match.group(2)
        fps = _fingerprints_from_citation_chunk(f"{author}, {year}")
        if fps and fps.issubset(allowed):
            return match.group(0)
        removed.append(f"{author} ({year})")
        return "a relevant study [insert verified source for this claim]"

    body = re.sub(
        r"\b([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?)\s*\(((?:19|20)\d{2}[a-z]?)\)",
        narrative_repl,
        body,
    )

    guarded = body.rstrip() + ("\n\n" + refs.lstrip() if refs else "")
    audit = citation_provenance_audit(guarded, profile, original_text=original_text)
    audit["removed_unverified_citations"] = sorted(set(removed))[:30]
    audit["removed_unverified_count"] = len(set(removed))
    guarded, reference_audit = enforce_verified_reference_list(guarded, profile, original_text=original_text)
    audit.update(reference_audit)
    return guarded.strip(), audit
