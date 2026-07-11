from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


# This module improves scholarly naturalness without introducing deliberate
# mistakes, changing evidence, or attempting to evade detection systems.
# It is intentionally deterministic so the same text receives the same edits.

_LEGACY_ARTIFACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\s+That is, it matters\.\s*", re.I), " "),
    (re.compile(r"\s+That matters\.\s*", re.I), " "),
    (
        re.compile(
            r"\s+This qualification matters (?:because|insofar as) it keeps the argument tied to the evidence rather than to an unsupported general claim\.\s*",
            re.I,
        ),
        " ",
    ),
)

_SAFE_PHRASE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\binsofar as of\b", re.I), "because of"),
    (re.compile(r"\binsofar as\b", re.I), "because"),
    (re.compile(r"\bthe present investigation\b", re.I), "the study"),
    (re.compile(r"\bthe results obtained\b", re.I), "the results"),
    (re.compile(r"\bas an illustration\b", re.I), "for example"),
    (re.compile(r"\bexemplifies how\b", re.I), "shows how"),
    (re.compile(r"\bnon[-\s]trivial function\b", re.I), "important role"),
    (re.compile(r"\bit is important to note that\b", re.I), ""),
    (re.compile(r"\bin today's world\b", re.I), "in the present context"),
    (re.compile(r"\bdelve into\b", re.I), "examine"),
    (re.compile(r"\bplays a crucial role\b", re.I), "is important"),
)

_GENERIC_PHRASES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bin today's world\b", re.I),
    re.compile(r"\bit is important to note\b", re.I),
    re.compile(r"\bdelve into\b", re.I),
    re.compile(r"\bplays a crucial role\b", re.I),
    re.compile(r"\bvarious factors\b", re.I),
    re.compile(r"\bthis highlights the importance\b", re.I),
    re.compile(r"\bthis study aims to contribute\b", re.I),
    re.compile(r"\bthe research problem is that\b", re.I),
    re.compile(r"\bthat matters\b", re.I),
    re.compile(r"\bthis qualification matters\b", re.I),
)

_PARAGRAPH_CONNECTOR_RE = re.compile(
    r"^(?P<connector>Moreover|Furthermore|Additionally|In addition|Besides this|It is also worth noting that)\s*,?\s+",
    re.I,
)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=(?:[A-Z\[]|\*\*))")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.I)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:%|\b)")
_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]+\]")
_URL_RE = re.compile(r"https?://\S+|\bdoi:\s*\S+|\b10\.\d{4,9}/\S+", re.I)
_CITATION_BLOCK_RE = re.compile(r"\([^()\n]{0,260}\b(?:19|20)\d{2}[a-z]?\b[^()\n]{0,260}\)", re.I)
_HEADING_LINE_RE = re.compile(r"(?m)^\s*(?:#{1,6}\s+.+|CHAPTER\s+(?:\d+|[A-Z]+)\s*$)", re.I)


def scholarly_humanizer_prompt_rules() -> list[str]:
    """Prompt rules shared by chapter generation and chapter strengthening."""
    return [
        "Write in a natural, disciplined scholarly voice rather than a promotional or template-like voice.",
        "Vary sentence length and paragraph density only where the argument requires it. Do not force fragments or artificial short sentences.",
        "Build substantive paragraphs around a clear claim, relevant evidence or a verification placeholder, interpretation, qualification where needed, and a link to the chapter argument or research objective.",
        "Use transitions that express the actual logical relationship, such as contrast, cause, condition, implication or limitation. Do not rotate synonyms mechanically.",
        "Avoid repeated paragraph openings, repeated generic connectors, inflated vocabulary and stock phrases such as 'it is important to note', 'plays a crucial role' and 'this highlights the importance'.",
        "Preserve the strength of claims. Do not replace cautious terms such as 'suggests' with stronger terms such as 'proves' or 'demonstrates' unless the evidence warrants it.",
        "Use formal British English, clear discipline-specific wording and moderate lexical variety. Prefer clarity over rare synonyms.",
        "Preserve all verified facts, statistics, dates, citations, references, equations, tables, headings, objectives, questions, hypotheses and bracketed action placeholders.",
        "Keep academic prose free from drafting commentary. Any unresolved confirmation, missing source, missing evidence or student instruction must appear as a separate [ACTION REQUIRED: ...] item, never as part of a thesis sentence.",
        "Do not use citations decoratively. Place each citation where it directly supports the preceding claim, compare sources where appropriate, and avoid leaving substantive evidence-based claims uncited.",
        "Do not add deliberate errors, sentence fragments, spelling variation, false hesitations or artificial drafting artefacts.",
        "Do not discuss AI detection or claim that the text is human-authored. The purpose of the pass is scholarly quality and alignment with the researcher's supplied voice and evidence.",
    ]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


def _std_dev(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _sentence_opening(sentence: str) -> str:
    cleaned = re.sub(r"^[\s\"'“”‘’([{]+", "", sentence or "")
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", cleaned.lower())
    return " ".join(words[:2])


def analyse_scholarly_style(text: str) -> dict[str, Any]:
    """Return a compact, explainable quality diagnostic for academic prose."""
    value = str(text or "")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip() and not _is_protected_block(part)]
    sentences: list[str] = []
    for paragraph in paragraphs:
        sentences.extend([item.strip() for item in _SENTENCE_RE.split(paragraph) if item.strip()])

    sentence_lengths = [_word_count(sentence) for sentence in sentences if _word_count(sentence)]
    paragraph_lengths = [_word_count(paragraph) for paragraph in paragraphs if _word_count(paragraph)]
    openings = [_sentence_opening(sentence) for sentence in sentences]
    opening_counts = Counter(opening for opening in openings if opening)
    repeated_openings = sum(max(0, count - 2) for count in opening_counts.values())
    generic_hits = sum(len(pattern.findall(value)) for pattern in _GENERIC_PHRASES)
    connector_hits = len(re.findall(r"(?im)^\s*(?:Moreover|Furthermore|Additionally|In addition)\s*,", value))
    long_sentences = sum(1 for length in sentence_lengths if length > 45)
    very_short_sentences = sum(1 for length in sentence_lengths if 0 < length < 5)

    score = 100
    score -= min(28, generic_hits * 4)
    score -= min(18, repeated_openings * 2)
    score -= min(12, max(0, connector_hits - 2) * 2)
    score -= min(18, long_sentences * 2)
    score -= min(10, very_short_sentences * 2)
    if len(sentence_lengths) >= 6 and _std_dev(sentence_lengths) < 5:
        score -= 8
    if len(paragraph_lengths) >= 4 and _std_dev(paragraph_lengths) < 18:
        score -= 5

    return {
        "score": max(0, min(100, score)),
        "word_count": _word_count(value),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "sentence_length_std_dev": round(_std_dev(sentence_lengths), 2),
        "paragraph_length_std_dev": round(_std_dev(paragraph_lengths), 2),
        "generic_phrase_hits": generic_hits,
        "repeated_sentence_openings": repeated_openings,
        "generic_connector_hits": connector_hits,
        "long_sentence_count": long_sentences,
        "very_short_sentence_count": very_short_sentences,
    }


def _is_protected_block(block: str) -> bool:
    value = str(block or "").strip()
    if not value:
        return True
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return True
    if lines[0].startswith("#") or re.fullmatch(r"CHAPTER\s+(?:\d+|[A-Z]+)", lines[0], re.I):
        return True
    if "```" in value or "$$" in value:
        return True
    if any(line.startswith("|") for line in lines) or any(re.match(r"^\|?\s*:?-{3,}", line) for line in lines):
        return True
    if all(re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", line) for line in lines):
        return True
    if len(lines) == 1 and len(lines[0].split()) <= 14 and lines[0].isupper():
        return True
    return False


def _apply_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _replace_preserving_case(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    return pattern.sub(lambda match: _apply_case(match.group(0), replacement), text)


def _split_long_semicolon_sentences(paragraph: str) -> str:
    sentences = _SENTENCE_RE.split(paragraph)
    revised: list[str] = []
    for sentence in sentences:
        if _word_count(sentence) <= 45 or ";" not in sentence:
            revised.append(sentence)
            continue
        parts = [part.strip() for part in sentence.split(";") if part.strip()]
        if len(parts) < 2 or any(_word_count(part) < 7 for part in parts):
            revised.append(sentence)
            continue
        for part in parts:
            clean = part.rstrip(".!?")
            if clean and clean[:1].islower():
                clean = clean[:1].upper() + clean[1:]
            revised.append(clean + ".")
    return " ".join(item.strip() for item in revised if item.strip())


def _refine_paragraph(paragraph: str, connector_seen: dict[str, int]) -> str:
    value = paragraph.strip()
    for pattern, replacement in _LEGACY_ARTIFACT_PATTERNS:
        value = pattern.sub(replacement, value)
    for pattern, replacement in _SAFE_PHRASE_REPLACEMENTS:
        value = _replace_preserving_case(value, pattern, replacement)

    connector_match = _PARAGRAPH_CONNECTOR_RE.match(value)
    if connector_match:
        key = connector_match.group("connector").lower()
        connector_seen[key] = connector_seen.get(key, 0) + 1
        # Keep the first occurrence of a connector. Later repetitions are usually
        # clearer without a generic transition than with a mechanically rotated one.
        if connector_seen[key] > 1:
            value = value[connector_match.end():]
            if value[:1].islower():
                value = value[:1].upper() + value[1:]

    value = _split_long_semicolon_sentences(value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([.!?])\s*([A-Z])", r"\1 \2", value)
    return value.strip()


def _signature(text: str) -> dict[str, list[str]]:
    value = str(text or "")
    return {
        "headings": _HEADING_LINE_RE.findall(value),
        "years": _YEAR_RE.findall(value),
        "numbers": _NUMBER_RE.findall(value),
        "placeholders": _PLACEHOLDER_RE.findall(value),
        "urls": _URL_RE.findall(value),
        "citation_blocks": _CITATION_BLOCK_RE.findall(value),
    }


def validate_humanizer_preservation(original: str, candidate: str, *, max_word_change_ratio: float = 0.06) -> tuple[bool, list[str]]:
    """Check that a style-only pass preserved core academic content."""
    reasons: list[str] = []
    before = _signature(original)
    after = _signature(candidate)
    for key in ("headings", "years", "numbers", "placeholders", "urls", "citation_blocks"):
        if before[key] != after[key]:
            reasons.append(f"{key} changed")

    original_words = max(1, _word_count(original))
    candidate_words = _word_count(candidate)
    ratio = abs(candidate_words - original_words) / original_words
    if ratio > max_word_change_ratio:
        reasons.append(f"word count changed by {ratio:.1%}")
    return not reasons, reasons


def humanize_scholarly_text(text: str, mode: str = "balanced") -> tuple[str, dict[str, Any]]:
    """Apply a deterministic, protected scholarly-style refinement pass.

    Modes:
    - off: return text unchanged
    - light: remove legacy artefacts and generic filler only
    - balanced: light pass plus safe long-sentence and connector refinement
    - deep: same protected local pass; the caller may add one model revision pass
    """
    original = str(text or "")
    normalised_mode = str(mode or "balanced").strip().lower()
    if normalised_mode in {"off", "none", "disabled", "0", "false"} or not original.strip():
        report = analyse_scholarly_style(original)
        report.update({"mode": "off", "applied": False, "preservation_passed": True, "preservation_issues": []})
        return original, report

    parts = re.split(r"(\n\s*\n)", original)
    connector_seen: dict[str, int] = {}
    output: list[str] = []
    reference_tail = False

    for part in parts:
        if not part or re.fullmatch(r"\n\s*\n", part):
            output.append(part)
            continue
        stripped = part.strip()
        if re.match(r"^#{1,6}\s*(?:References|Source Use Audit)\b", stripped, re.I):
            reference_tail = True
        if reference_tail or _is_protected_block(part):
            output.append(part)
            continue
        refined = _refine_paragraph(part, connector_seen)
        output.append(refined)

    candidate = "".join(output)
    candidate = re.sub(r"[ \t]+\n", "\n", candidate)
    candidate = re.sub(r"\n{3,}", "\n\n", candidate).strip()

    original_words = max(1, _word_count(original))
    local_change_limit = max(0.06, min(0.40, 40 / original_words))
    valid, issues = validate_humanizer_preservation(
        original,
        candidate,
        max_word_change_ratio=local_change_limit,
    )
    if not valid:
        report = analyse_scholarly_style(original)
        report.update({
            "mode": normalised_mode,
            "applied": False,
            "preservation_passed": False,
            "preservation_issues": issues,
        })
        return original, report

    report = analyse_scholarly_style(candidate)
    report.update({
        "mode": normalised_mode,
        "applied": candidate != original,
        "preservation_passed": True,
        "preservation_issues": [],
        "score_before": analyse_scholarly_style(original).get("score", 0),
        "score_after": report.get("score", 0),
    })
    return candidate, report
