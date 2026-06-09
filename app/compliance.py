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

        density_result = _check_citation_density(section_paras or paragraphs)
        items.append(
            {
                "section_id": section["section_id"],
                "section_title": section_title,
                "requirement": "Substantive claims in this section should be supported with accurate in-text citations or clear source placeholders.",
                "status": density_result["status"],
                "evidence": density_result["evidence"],
                "suggested_action": density_result["suggested_action"],
            }
        )


    reference_result = _check_references_section(paragraphs)
    items.append(
        {
            "section_id": "chapter_references",
            "section_title": "Chapter References",
            "requirement": "Chapter should include a References section containing sources actually cited in the chapter.",
            "status": reference_result["status"],
            "evidence": reference_result["evidence"],
            "suggested_action": reference_result["suggested_action"],
        }
    )

    audit_result = _check_source_use_audit(paragraphs)
    items.append(
        {
            "section_id": "source_use_audit",
            "section_title": "Source Use Audit",
            "requirement": "Where source-search results were used or attached, the chapter should include a Source Use Audit explaining which searched sources were cited or excluded.",
            "status": audit_result["status"],
            "evidence": audit_result["evidence"],
            "suggested_action": audit_result["suggested_action"],
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

    if "citation" in rule_lower or "cite" in rule_lower or "in-text" in rule_lower:
        return _check_citation_rule(rule, section_paras)

    if "statistics" in rule_lower or "statistic" in rule_lower or "factual" in rule_lower or "facts" in rule_lower:
        return _check_factual_evidence_rule(rule, section_paras)

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


def _check_citation_rule(rule: str, section_paras: list[tuple[int, str]]) -> dict[str, str]:
    for number, para in section_paras:
        if _has_intext_citation(para) or _has_source_placeholder(para):
            status = "Passed" if _has_intext_citation(para) else "Weak"
            action = "None" if status == "Passed" else "Replace the placeholder with a verified source and accurate in-text citation."
            return {
                "status": status,
                "evidence": f"Paragraph {number}: {_snippet(para)}",
                "suggested_action": action,
            }
    return {
        "status": "Missing",
        "evidence": "No in-text citation or source placeholder was found in this section.",
        "suggested_action": f"Add relevant accurate in-text citation evidence for this requirement: {rule}",
    }


def _check_factual_evidence_rule(rule: str, section_paras: list[tuple[int, str]]) -> dict[str, str]:
    for number, para in section_paras:
        if _has_statistical_or_factual_evidence(para):
            return {
                "status": "Passed",
                "evidence": f"Paragraph {number}: {_snippet(para)}",
                "suggested_action": "None",
            }
        if "[insert current statistic" in para.lower() or "[insert statistic" in para.lower() or "[insert evidence" in para.lower():
            return {
                "status": "Weak",
                "evidence": f"Paragraph {number}: {_snippet(para)}",
                "suggested_action": "Replace the placeholder with verified facts, statistics, policy evidence, or empirical evidence.",
            }
    return {
        "status": "Missing",
        "evidence": "No clear statistic, factual evidence, or evidence placeholder was found in this section.",
        "suggested_action": f"Add verified facts/statistics or a clear evidence placeholder for this requirement: {rule}",
    }


def _has_intext_citation(text: str) -> bool:
    # Author-year examples: (Smith, 2024), Smith (2024), Smith and Mensah (2023), Smith et al. (2022)
    patterns = [
        r"\([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+(?:\s+(?:&|and)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+|\s+et\s+al\.)?,\s*(?:19|20)\d{2}[a-z]?\)",
        r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+|\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\)",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _has_statistical_or_factual_evidence(text: str) -> bool:
    evidence_words = ["percent", "percentage", "rate", "ratio", "index", "report", "survey", "census", "dataset", "statistics", "statistical", "policy", "official", "ministry", "world bank", "ghana statistical service", "oecd", "unesco", "who"]
    has_number = bool(re.search(r"(?:\d+(?:\.\d+)?\s?%|\b\d+(?:,\d{3})*(?:\.\d+)?\b)", text))
    has_evidence_word = any(word in text.lower() for word in evidence_words)
    return has_number or has_evidence_word


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


def _check_references_section(paragraphs: list[str]) -> dict[str, str]:
    text = "\n\n".join(paragraphs or [])
    match = re.search(r"(?im)^#{0,3}\s*(references|reference list)\b", text)
    if not match:
        return {
            "status": "Missing",
            "evidence": "No References section was found at the end of the chapter.",
            "suggested_action": "Add a References section containing only sources cited in the chapter body.",
        }
    refs_text = text[match.end():].strip()
    if _has_intext_citation(refs_text) or re.search(r"\b(19|20)\d{2}\b", refs_text):
        return {
            "status": "Passed",
            "evidence": "References section found with apparent author-year entries.",
            "suggested_action": "None",
        }
    return {
        "status": "Weak",
        "evidence": "References heading was found, but the entries appear incomplete or missing.",
        "suggested_action": "Add complete reference entries for sources actually cited in the chapter.",
    }


def _check_source_use_audit(paragraphs: list[str]) -> dict[str, str]:
    text = "\n\n".join(paragraphs or [])
    match = re.search(r"(?im)^#{0,3}\s*source\s+use\s+audit\b", text)
    if not match:
        return {
            "status": "Weak",
            "evidence": "No Source Use Audit section was found. This is acceptable only when no source-search results were attached.",
            "suggested_action": "If the source finder was used, add a Source Use Audit after the References section showing cited, not cited, and excluded sources with reasons.",
        }
    audit_text = text[match.end():].strip()
    if re.search(r"(?i)\b(cited|not cited|excluded|not relevant|source key|relevance tier)\b", audit_text):
        return {
            "status": "Passed",
            "evidence": "Source Use Audit section found with citation/exclusion decisions.",
            "suggested_action": "None",
        }
    return {
        "status": "Weak",
        "evidence": "Source Use Audit heading was found, but the decisions or reasons appear incomplete.",
        "suggested_action": "Use columns such as Source Key, Relevance Tier, Decision, and Reason.",
    }
