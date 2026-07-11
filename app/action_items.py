from __future__ import annotations

import re

_ACTION_RE = re.compile(
    r"\[(?P<body>(?:action\s+required\s*\d*\s*:\s*)?"
    r"(?:insert|verify|confirm|provide|supply|complete|replace|check|add|update|obtain|state|specify|include|conduct|resolve|revise|review|clarify|report|identify|upload|attach|calculate|test|assess|determine|seek|perform|run|collect|address)\b[^\]\n]*)\]",
    flags=re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|CHAPTER\s+(?:\d+|[A-Z]+)|\d+(?:\.\d+){0,4}\s+.+)$",
    flags=re.IGNORECASE,
)
_META_RE = re.compile(
    r"\b(?:requires? confirmation|retained as attention placeholders?|the following evidence should be inserted|"
    r"at this stage.*requires? the following supporting evidence|project details require confirmation|"
    r"confirm whether to retain this guidance note|the available project information does not yet include|"
    r"the following details? (?:is|are) required|the user should|the student should)\b",
    flags=re.IGNORECASE,
)
_ACTION_APPENDIX_RE = re.compile(r"(?im)^#{0,3}\s*USER ACTIONS REQUIRED\s*$")


def _clean_residue(text: str) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([,:;])\s*(?:,|and\s*)?(?=[.!?]|$)", ".", value, flags=re.I)
    value = re.sub(r"\b(?:and|or)\s*([.!?])", r"\1", value, flags=re.I)
    value = re.sub(r"\.{2,}", ".", value)
    value = re.sub(r"\s+([)])", r"\1", value)
    value = re.sub(r"([(])\s+", r"\1", value)
    value = value.strip(" ,;:")
    return value


def _normalise_action(body: str) -> str:
    value = re.sub(r"^action\s+required\s*\d*\s*:\s*", "", str(body or ""), flags=re.I).strip()
    value = re.sub(r"\s+", " ", value).strip(" .;:")
    if not value:
        return ""
    return value[:1].upper() + value[1:]


def _scholarly_residue(block: str, residue: str, placeholder_ratio: float) -> str:
    """Keep genuine thesis prose but remove commentary whose main purpose is instruction."""
    value = residue.strip()
    if not value:
        return ""
    if _META_RE.search(block) and (placeholder_ratio > 0.16 or len(value.split()) < 32):
        sentences = re.split(r"(?<=[.!?])\s+", value)
        sentences = [sentence.strip() for sentence in sentences if sentence.strip() and not _META_RE.search(sentence)]
        value = " ".join(sentences).strip()
    return value


def detach_action_items(text: str) -> str:
    """Detach placeholders from prose and place each red action beside its source paragraph.

    The historical implementation collected all actions at the end of the chapter. That made
    it difficult for a student to identify the exact sentence or paragraph needing attention.
    This function now keeps the chapter narrative clean and inserts each complete bracketed
    action immediately after the affected paragraph or at the original action-only location.
    The DOCX exporter colours the whole bracketed action red.
    """
    source = str(text or "")
    if not source.strip():
        return source

    # Remove a legacy bottom appendix. New model prompts and the logic below keep actions
    # beside the affected material instead. This prevents duplicate actions after reprocessing.
    appendix_match = _ACTION_APPENDIX_RE.search(source)
    if appendix_match:
        source = source[:appendix_match.start()].rstrip()

    blocks = re.split(r"\n\s*\n", source)
    output: list[str] = []
    seen: set[str] = set()
    action_number = 0

    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue

        matches = list(_ACTION_RE.finditer(stripped))
        if not matches:
            output.append(stripped)
            continue

        residue = _clean_residue(_ACTION_RE.sub("", stripped))
        placeholder_chars = sum(len(match.group(0)) for match in matches)
        placeholder_ratio = placeholder_chars / max(1, len(stripped))
        residue = _scholarly_residue(stripped, residue, placeholder_ratio)
        if residue:
            output.append(residue)

        # Place each unique action immediately after the paragraph from which it was removed.
        for match in matches:
            action = _normalise_action(match.group("body"))
            key = action.casefold()
            if not action or key in seen:
                continue
            seen.add(key)
            action_number += 1
            output.append(f"[ACTION REQUIRED {action_number}: {action.rstrip('.')}.]")

    return "\n\n".join(output).strip()
