from __future__ import annotations

import re
from typing import Iterable

_ACTION_RE = re.compile(
    r"\[(?P<body>(?:action\s+required\s*\d*\s*:\s*)?"
    r"(?:insert|verify|confirm|provide|supply|complete|replace|check|add|update|obtain|state|specify|include|conduct|resolve|revise)\b[^\]\n]*)\]",
    flags=re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|CHAPTER\s+(?:\d+|[A-Z]+)|\d+(?:\.\d+){0,4}\s+.+)$",
    flags=re.IGNORECASE,
)
_META_RE = re.compile(
    r"\b(?:requires? confirmation|retained as attention placeholders?|the following evidence should be inserted|"
    r"at this stage.*requires? the following supporting evidence|project details require confirmation|"
    r"confirm whether to retain this guidance note|the available project information does not yet include)\b",
    flags=re.IGNORECASE,
)


def _clean_residue(text: str) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([,:;])\s*(?:,|and\s*)?(?=[.!?]|$)", ".", value, flags=re.I)
    value = re.sub(r"\b(?:and|or)\s*([.!?])", r"\1", value, flags=re.I)
    value = re.sub(r"\.{2,}", ".", value)
    value = value.strip(" ,;:")
    return value


def detach_action_items(text: str) -> str:
    """Move user-facing placeholders out of academic prose into a separate red-action list.

    This keeps comments and missing-evidence instructions visibly separate from the chapter
    narrative while preserving every action for the user.
    """
    source = str(text or "")
    if not source.strip():
        return source

    # Avoid duplicating an existing action appendix.
    source = re.split(r"(?im)^#{0,3}\s*USER ACTIONS REQUIRED\s*$", source, maxsplit=1)[0].rstrip()
    blocks = re.split(r"\n\s*\n", source)
    output: list[str] = []
    actions: list[tuple[str, str]] = []
    current_heading = "General"

    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(stripped) and "[" not in stripped:
            current_heading = re.sub(r"^#{1,6}\s*", "", stripped).strip()
            output.append(stripped)
            continue

        found = [m.group("body").strip() for m in _ACTION_RE.finditer(stripped)]
        if not found:
            output.append(stripped)
            continue

        for item in found:
            item = re.sub(r"^action\s+required\s*\d*\s*:\s*", "", item, flags=re.I).strip()
            if item:
                actions.append((current_heading, item))

        residue = _clean_residue(_ACTION_RE.sub("", stripped))
        placeholder_chars = sum(len(m.group(0)) for m in _ACTION_RE.finditer(stripped))
        placeholder_ratio = placeholder_chars / max(1, len(stripped))
        # Commentary dominated by instructions should not remain as thesis prose.
        if residue:
            if _META_RE.search(stripped) and (placeholder_ratio > 0.20 or len(residue.split()) < 28):
                # Preserve any genuine scholarly sentence that follows the meta-commentary.
                sentences = re.split(r"(?<=[.!?])\s+", residue)
                scholarly = [sentence for sentence in sentences if sentence.strip() and not _META_RE.search(sentence)]
                residue = " ".join(scholarly).strip()
            if residue:
                output.append(residue)

    if actions:
        output.extend(["", "## USER ACTIONS REQUIRED"])
        seen: set[tuple[str, str]] = set()
        for location, action in actions:
            key = (location.lower(), action.lower())
            if key in seen:
                continue
            seen.add(key)
            label = f"{action.rstrip('.')} — Location: {location}"
            output.append(f"[ACTION REQUIRED {len(seen)}: {label}.]")

    return "\n\n".join(output).strip()
