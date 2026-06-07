from __future__ import annotations

import re
from typing import Any

from app.ai_service import split_paragraphs
from app.template_store import selected_sections

KEYWORD_BANK = {
    "global": ["global", "international", "world", "worldwide", "regional", "national", "local", "context"],
    "problem": ["problem", "challenge", "gap", "limited", "weakness", "concern", "issue", "focus"],
    "evidence": ["evidence", "study", "studies", "data", "report", "policy", "statistics", "empirical", "research"],
    "objective": ["objective", "examine", "analyse", "assess", "determine", "evaluate", "investigate", "explore"],
    "question": ["research question", "question", "what", "how", "to what extent", "why"],
    "hypothesis": ["hypothesis", "hypotheses", "significant", "relationship", "effect", "influence", "association"],
    "theory": ["theory", "theoretical", "framework", "model", "underpin", "conceptual"],
    "method": ["method", "design", "population", "sample", "sampling", "instrument", "data", "analysis", "validity", "reliability", "ethics"],
    "finding": ["finding", "result", "revealed", "showed", "indicated", "significant", "mean", "coefficient", "theme"],
    "recommendation": ["recommend", "should", "policy", "practice", "stakeholder", "implement"],
}

RULE_HINTS = [
    ("global", "global"),
    ("local", "global"),
    ("context", "global"),
    ("problem", "problem"),
    ("gap", "problem"),
    ("evidence", "evidence"),
    ("empirical", "evidence"),
    ("policy", "evidence"),
    ("objective", "objective"),
    ("measurable", "objective"),
    ("research question", "question"),
    ("hypothesis", "hypothesis"),
    ("theor", "theory"),
    ("conceptual", "theory"),
    ("philosophy", "method"),
    ("ontology", "method"),
    ("epistemology", "method"),
    ("design", "method"),
    ("sampling", "method"),
    ("sample", "method"),
    ("validity", "method"),
    ("reliability", "method"),
    ("ethic", "method"),
    ("result", "finding"),
    ("finding", "finding"),
    ("discussion", "finding"),
    ("recommend", "recommendation"),
    ("future research", "recommendation"),
]


def check_chapter(chapter_number: int, selected_section_ids: list[str], draft: str) -> dict[str, Any]:
    sections = selected_sections(chapter_number, selected_section_ids)
    paragraphs = split_paragraphs(draft)
    items: list[dict[str, Any]] = []

    for section in sections:
        section_title = section["section_title"]
        section_paras = _section_paragraphs(section_title, paragraphs)
        for rule in section.get("rules", []):
            result = _check_rule(rule, section_paras or paragraphs)
            items.append(
                {
                    "section_id": section["section_id"],
                    "section_title": section_title,
                    "requirement": rule,
                    "status": result["status"],
                    "evidence": result["evidence"],
                    "suggested_action": result["suggested_action"],
                }
            )

    score = _score(items)
    return {"chapter_number": chapter_number, "score_percent": score, "items": items}


def _section_paragraphs(section_title: str, paragraphs: list[str]) -> list[tuple[int, str]]:
    indexed = list(enumerate(paragraphs, start=1))
    starts: list[int] = []
    heading_pattern = re.compile(re.escape(section_title), re.IGNORECASE)
    for idx, text in indexed:
        if heading_pattern.search(text) or _normalise(section_title) in _normalise(text):
            starts.append(idx)
    if not starts:
        return []

    start = starts[0]
    collected: list[tuple[int, str]] = []
    for idx, text in indexed:
        if idx <= start:
            continue
        if re.match(r"^(#{1,3}\s+)?\d+(\.\d+)*\s+.+", text.strip()) and collected:
            break
        collected.append((idx, text))
    return collected


def _check_rule(rule: str, section_paras: list[tuple[int, str]]) -> dict[str, str]:
    rule_lower = rule.lower()
    hint_key = None
    for needle, bank_key in RULE_HINTS:
        if needle in rule_lower:
            hint_key = bank_key
            break
    keywords = KEYWORD_BANK.get(hint_key or "evidence", [])

    best: tuple[int, str, int] | None = None
    for number, para in section_paras:
        text = para.lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits and (best is None or hits > best[2]):
            best = (number, para, hits)

    if best and best[2] >= 2:
        return {
            "status": "Passed",
            "evidence": f"Paragraph {best[0]}: {_snippet(best[1])}",
            "suggested_action": "None",
        }
    if best:
        return {
            "status": "Weak",
            "evidence": f"Paragraph {best[0]}: {_snippet(best[1])}",
            "suggested_action": f"Strengthen this requirement: {rule}",
        }
    return {
        "status": "Missing",
        "evidence": "No clear paragraph evidence found in the draft.",
        "suggested_action": f"Add content that satisfies this requirement: {rule}",
    }


def _score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    values = {"Passed": 1.0, "Weak": 0.5, "Missing": 0.0}
    total = sum(values.get(item["status"], 0.0) for item in items)
    return round((total / len(items)) * 100, 1)


def _snippet(text: str, max_len: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
