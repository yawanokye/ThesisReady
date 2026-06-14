from __future__ import annotations

import json
import os
import re
import random
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

from app.template_store import get_chapter, selected_sections

load_dotenv()


# ----------------------------------------------------------------------
# DEEPSEEK CLIENT (ONLY)
# ----------------------------------------------------------------------

def _safe_get_deepseek_client():
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        return OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com",
        )
    except Exception:
        return None


def _call_deepseek(
    prompt: str,
    instructions: str,
    temperature: float = 0.7,
    max_tokens: int = 8000,
) -> str:
    """Make a call to DeepSeek chat completion. Returns empty string on failure."""
    client = _safe_get_deepseek_client()
    if client is None:
        return ""
    model = os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=90,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"DeepSeek call failed: {e}")
        return ""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except Exception:
        return default


# ----------------------------------------------------------------------
# THESIS REQUIREMENTS (unchanged)
# ----------------------------------------------------------------------

def _reference_currency_requirements() -> dict[str, Any]:
    current_year = datetime.now().year
    start_year = current_year - 5
    return {
        "current_year": current_year,
        "recent_reference_window": f"{start_year}-{current_year}",
        "rule": (
            f"Aim for at least 70% of substantive references to be from {start_year}-{current_year}. "
            "Where current references do not exist, use the strongest credible available sources. "
            "Older sources are acceptable for foundational theories, classic models, scarce-literature areas, and essential earlier studies."
        ),
        "integrity_guard": (
            "Do not fabricate citations or reference-list entries. Use sources supplied by the student or sources that can be stated with confidence. "
            "If no credible source details are available, insert a clear bracketed placeholder such as "
            f"[insert verified recent source if available, {start_year}-{current_year}] or [insert credible available source]."
        ),
    }


def _citation_and_evidence_requirements(chapter_number: int) -> dict[str, Any]:
    current_year = datetime.now().year
    start_year = current_year - 5
    common_rules = [
        "Include relevant and accurate in-text citations in every substantive section of the write-up.",
        "Use author-year citation style unless the user or institution requests another style.",
        "Do not cite a source unless the source was supplied by the student, included in the profile/reference notes, present in uploaded material, or can be stated confidently without guessing.",
        "Where a citation is needed but no reliable source details are available, insert a red bracketed placeholder such as [insert verified source for this claim] rather than inventing a citation.",
        "Support factual claims with evidence. Use statistics, policy evidence, institutional records, peer-reviewed studies, official reports, or credible datasets where available.",
        f"Prioritise recent references from {start_year}-{current_year}, but use older sources when they are foundational theories, classic models, or the best credible evidence available.",
        "Do not create a reference list entry for any source unless enough accurate bibliographic information is supplied or known with confidence.",
    ]
    if chapter_number == 1:
        common_rules.extend([
            "The Background and Statement of the Problem must be evidence-led. They should include relevant factual evidence and accurate statistics where available.",
            "The Statement of the Problem must not rely on unsupported claims. It should identify the problem, provide evidence that the problem exists, show who or what is affected, and state the research gap.",
            "Use current and context-relevant statistics from credible sources such as official reports, national statistics, industry reports, policy documents, or peer-reviewed studies where supplied or confidently known.",
            "Where exact statistics are not supplied, do not invent figures. Use placeholders such as [insert current statistic from Ghana Statistical Service, World Bank, ministry report, institutional records, or peer-reviewed study] and keep the argument coherent.",
        ])
    if chapter_number == 2:
        common_rules.extend([
            "The literature review must cite studies accurately when discussing theories, concepts, empirical findings, contradictions, and gaps.",
            "Every empirical-study paragraph should identify the author/year, context, method, key finding, and relevance to the current study where available.",
        ])
    if chapter_number == 4:
        common_rules.extend([
            "Do not invent results or statistics. Interpret only the uploaded or supplied results.",
            "In the discussion, cite relevant theory and prior studies when explaining whether the findings agree, contradict, or extend existing evidence.",
        ])
    return {
        "citation_style": "Author-year in-text citations by default, unless another style is supplied.",
        "recent_reference_window": f"{start_year}-{current_year}",
        "rules": common_rules,
    }


def _level_depth_requirements(profile: dict[str, Any]) -> dict[str, str]:
    level = (profile.get("level") or "Bachelors").strip()
    guidance_map = {
        "Bachelors": (
            "Write as an expert undergraduate student. Use clear definitions, relevant context, logical explanation, basic critical discussion, "
            "and a defensible but not overly complex methodology."
        ),
        "Non-Research Masters": (
            "Write as an expert non-research master's student. Emphasise professional application, practical relevance, clear synthesis, "
            "methodological clarity, and implications for practice or institutions."
        ),
        "Research Masters (e.g. MPhil)": (
            "Write as an expert research master's student. Provide deeper critical synthesis, objective-driven literature review, explicit gaps, "
            "theory-method alignment, and rigorous methodological justification."
        ),
        "Professional Doctorate (e.g. DBA, DEd)": (
            "Write as an expert professional doctorate student. Frame the work around a significant professional or organisational problem, "
            "show advanced applied scholarship, demonstrate practice-based contribution, and defend methodological choices strongly."
        ),
        "PhD": (
            "Write as an expert doctoral student. Provide publication-quality academic argument, deep theoretical engagement, advanced critical synthesis, "
            "clear originality, rigorous methodology, and a defensible contribution to knowledge."
        ),
    }
    guidance = profile.get("academic_level_guidance") or guidance_map.get(level, guidance_map["Bachelors"])
    return {"selected_level": level, "depth_guidance": guidance}


def _normalise_level_name(profile: dict[str, Any]) -> str:
    level = str(profile.get("level") or profile.get("academic_level") or "Bachelors").strip().lower()
    if "phd" in level or "doctor" in level:
        return "doctoral"
    if "research" in level or "mphil" in level:
        return "research_masters"
    if "master" in level:
        return "masters"
    return "bachelors"


def _chapter_length_depth_requirements(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_count: int = 0,
) -> dict[str, Any]:
    level = _normalise_level_name(profile)
    table = {
        "bachelors": {
            1: (2800, 3600),
            2: (4200, 6500),
            3: (3000, 4200),
            4: (3200, 4800),
            5: (2200, 3200),
            7: (2500, 3800),
        },
        "masters": {
            1: (3500, 5000),
            2: (6500, 9000),
            3: (4200, 6000),
            4: (4500, 7000),
            5: (3000, 4500),
            7: (3500, 5200),
        },
        "research_masters": {
            1: (4200, 6000),
            2: (8000, 12000),
            3: (5500, 8000),
            4: (6000, 9000),
            5: (3800, 5500),
            7: (4500, 6500),
        },
        "doctoral": {
            1: (5500, 8000),
            2: (12000, 18000),
            3: (8000, 12000),
            4: (8500, 13000),
            5: (5000, 8000),
            7: (6500, 9500),
        },
    }
    minimum, target = table.get(level, table["bachelors"]).get(int(chapter_number or 1), (2500, 3800))
    if selected_section_count and selected_section_count < 5:
        scale = max(0.55, selected_section_count / 8)
        minimum = int(minimum * scale)
        target = int(target * scale)
    return {
        "normalised_level": level,
        "minimum_words": minimum,
        "target_words": target,
        "rule": (
            f"For this level and chapter, produce a substantive chapter of at least about {minimum:,} words, "
            f"with a preferred working range up to about {target:,} words when most standard sections are selected. "
            "Do not pad with filler; expand through evidence, citations, explanation, local context, methodological alignment, and precise placeholders."
        ),
        "quality_gate": [
            "A Bachelor chapter must still read like a complete thesis chapter, not a short assignment answer.",
            "Do not compress Background, Statement of the Problem, Significance, Delimitations, and Limitations into thin paragraphs.",
            "Most substantive paragraphs should contain either an in-text citation from the supplied/source-bank references, a supplied evidence anchor, or a precise placeholder for a missing source/statistic.",
            "If the draft is below the minimum word guidance, expand analytically before finalising.",
        ],
    }


def _uploaded_results_for_chapter(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    uploaded = profile.get("uploaded_results") or {}
    result = uploaded.get(str(chapter_number))
    if chapter_number == 4 and not result:
        result = uploaded.get("4")
    return result or {}


def _normalise_author_for_citation(author: str) -> str:
    author = str(author or "").strip()
    if not author:
        return "[Author]"
    parts = author.replace(",", " ").split()
    return parts[-1] if parts else author


def _citation_label_for_source(src: dict[str, Any]) -> str:
    authors = src.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    year = str(src.get("year") or "n.d.").strip() or "n.d."
    cleaned = [_normalise_author_for_citation(a) for a in authors if str(a).strip()]
    if not cleaned:
        return f"([Author], {year})"
    if len(cleaned) == 1:
        return f"({cleaned[0]}, {year})"
    if len(cleaned) == 2:
        return f"({cleaned[0]} & {cleaned[1]}, {year})"
    return f"({cleaned[0]} et al., {year})"


def _source_key(src: dict[str, Any]) -> str:
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:100]
    return "title:" + title


def _merged_source_bank(profile: dict[str, Any], limit: int = 24) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for container_key in ["source_bank", "attached_sources"]:
        value = profile.get(container_key) or []
        if isinstance(value, list):
            collected.extend([v for v in value if isinstance(v, dict)])
    retrieved = profile.get("retrieved_sources") or {}
    value = retrieved.get("sources") or []
    if isinstance(value, list):
        collected.extend([v for v in value if isinstance(v, dict)])
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for src in collected:
        key = _source_key(src)
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(src)
        item["citation_key"] = f"SRC{len(merged) + 1}"
        item["in_text_citation"] = _citation_label_for_source(item)
        if not item.get("apa_hint"):
            title = item.get("title", "[Title]")
            authors = item.get("authors") or ["[Author]"]
            if isinstance(authors, str):
                authors = [authors]
            year = item.get("year") or "n.d."
            source = item.get("source") or ""
            doi = item.get("doi") or ""
            doi_text = f" https://doi.org/{doi}" if doi else ""
            item["apa_hint"] = f"{', '.join(map(str, authors))} ({year}). {title}. {source}.{doi_text}".strip()
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _retrieved_sources_for_prompt(profile: dict[str, Any], chapter_number: int | None = None) -> dict[str, Any]:
    retrieved = profile.get("retrieved_sources") or {}
    source_bank = _merged_source_bank(profile)
    compact_sources = []
    for src in source_bank:
        compact_sources.append({
            "citation_key": src.get("citation_key", ""),
            "title": src.get("title", ""),
            "authors": src.get("authors", []),
            "year": src.get("year", ""),
            "source": src.get("source", ""),
            "doi": src.get("doi", ""),
            "url": src.get("url", ""),
            "abstract": src.get("abstract", ""),
            "database": src.get("database", ""),
            "relevance_tier": src.get("relevance_tier", "unclassified"),
            "relevance_reason": src.get("relevance_reason", "No relevance explanation supplied."),
            "suggested_use": src.get("suggested_use", "Use only where it directly supports the claim."),
            "in_text_citation": src.get("in_text_citation", ""),
            "reference_entry_hint": src.get("apa_hint", ""),
        })
    compact_sources.sort(key=lambda x: ({"highly_relevant":3, "partly_relevant":2}.get(x.get("relevance_tier",""), 0)), reverse=True)
    return {
        "query": retrieved.get("query", ""),
        "source_count": len(compact_sources),
        "sources": compact_sources,
        "source_use_rules": [
            "Use retrieved_sources only where directly relevant.",
            "Do not cite not_relevant sources.",
            "If a source is not directly needed, use a placeholder instead.",
        ]
    }


def _student_contribution_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    contribution = profile.get("student_contribution") or {}
    if not isinstance(contribution, dict):
        contribution = {}
    return {
        "draft_maturity": contribution.get("draft_maturity") or profile.get("draft_maturity") or "Supervisor-ready draft",
        "central_argument": contribution.get("central_argument") or "",
        "local_context_notes": contribution.get("local_context_notes") or "",
        "evidence_anchors": contribution.get("evidence_anchors") or "",
        "supervisor_comments": contribution.get("supervisor_comments") or "",
        "preferred_style": contribution.get("preferred_style") or "",
        "writing_sample": contribution.get("writing_sample") or "",
        "phrases_to_avoid": contribution.get("phrases_to_avoid") or "",
        "human_revision_pass_requested": bool(contribution.get("human_revision_pass", True)),
    }


def _chapter_specific_requirements(chapter_number: int) -> list[str]:
    common = [
        "Use valid markdown for headings, paragraphs, lists, and tables.",
        "Keep paragraphs coherent and academic, with clear topic sentences, developed reasoning, and smooth transitions.",
        "Write with a natural, polished academic voice rather than a template-like or mechanical tone.",
        "Make the chapter read as a coherent scholarly argument, not a collection of disconnected notes.",
        "Avoid generic filler, excessive repetition, unsupported claims, vague expressions, and very short choppy sentences.",
        "Treat the chapter as part of a completed project, dissertation, or thesis. Do not use future-tense proposal wording such as 'will examine', 'will collect', 'will use', 'will adopt', 'will analyse', or 'will be conducted'.",
        "Do not mention that the writing is designed to meet a selected academic level, checklist, template, or software requirement. The chapter should read like normal scholarly prose.",
    ]
    if chapter_number == 1:
        return common + [
            "Frame the statement of the problem through evidence, contradiction, gap, or unresolved practical concern rather than beginning with 'The research problem is that...'.",
            "Use connected paragraphs that move from context to evidence, evidence to gap, and gap to research focus.",
            "Use accurate statistics and factual evidence where supplied or confidently known. Where statistics are needed but not supplied, insert a bracketed placeholder rather than inventing figures.",
        ]
    if chapter_number == 2:
        return common + [
            "Organise the literature review around the student's selected structure and research objectives.",
            "Where a literature gap table is requested, create a clean markdown table, not a paragraph.",
            "Use this exact table structure for a literature gap table: | Research Objective | Key Authors and Year | Context of Study | Method Used | Key Findings | Identified Gap | Relevance to Current Study |.",
            "Each research objective should have at least one separate row in the literature gap table.",
            "Use concise table entries. Do not merge all studies, methods, findings, and gaps into one long cell.",
            "Where the student has not supplied authors or studies, use placeholders such as [insert author and year] rather than inventing sources.",
        ]
    if chapter_number == 3:
        return common + [
            "Write Chapter Three as a completed final project, dissertation, or thesis chapter, not as a proposal.",
            "Use past tense and completed-study wording throughout Chapter Three.",
            "Do not use proposal-style future tense.",
            "If a detail has not been supplied, use a past-tense placeholder, for example '[insert sampling procedure used]'.",
            "The methodology chapter should follow a strong doctoral-methods structure: introduction, research philosophy, research approach, study design, target population, sample size and sampling procedure, operationalisation and measurement, sources of data, data collection instrument, reliability and validity, ethical considerations, and data processing and analysis.",
        ]
    if chapter_number == 4:
        return common + [
            "Write a clean Results/Data Analysis and Discussion chapter. Do not refer to the file as 'uploaded results', 'the uploaded output', or similar.",
            "Use only results actually supplied in uploaded files or student answers. Do not invent coefficients, p-values, sample sizes, reliability values, model fit statistics, themes, quotations or percentages.",
            "Where a required result is missing, create a clean placeholder table with bracketed red placeholders and add a short advisory sentence telling the user the exact result/output to obtain.",
            "Advise what should go to appendix, including raw software output, long diagnostics, full correlation matrices, full interview transcripts, questionnaires, codebooks and lengthy robustness checks.",
            "Interpret results beyond description and link discussion to theory, prior studies and context using relevant citations.",
        ]
    if chapter_number == 5:
        return common + [
            "Base summaries, conclusions, recommendations, and future research suggestions only on supplied findings.",
            "Ensure each recommendation can be traced to a finding.",
        ]
    return common


def _effective_chapter_title(chapter: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    if int(chapter_number or 0) == 6:
        custom_title = str(profile.get("other_chapter_title") or "").strip()
        if custom_title:
            return custom_title
        return "Others"
    if int(chapter_number or 0) == 7:
        return "Supplementary Methods Chapter"
    return str(chapter.get("chapter_title") or "").strip() or "Chapter"


def build_drafting_prompt(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
) -> str:
    chapter = get_chapter(chapter_number)
    effective_chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}

    section_payload = []
    for section in sections:
        section_payload.append({
            "section_id": section["section_id"],
            "section_title": section["section_title"],
            "guiding_questions": section.get("guiding_questions", []),
            "rules": section.get("rules", []),
            "student_answers": answers.get(section["section_id"], {}),
        })

    prompt = {
        "task": "Draft a full academic project chapter using selected institutional guideline sections.",
        "chapter": {
            "chapter_number": chapter_number,
            "chapter_title": effective_chapter_title,
        },
        "project_profile": profile,
        "selected_academic_level_and_depth": _level_depth_requirements(profile),
        "chapter_length_and_depth_requirements": _chapter_length_depth_requirements(profile, chapter_number, len(section_payload)),
        "reference_currency_requirements": _reference_currency_requirements(),
        "citation_and_evidence_requirements": _citation_and_evidence_requirements(chapter_number),
        "student_contribution_and_style_controls": _student_contribution_requirements(profile),
        "analysis_evidence_for_this_chapter": _uploaded_results_for_chapter(profile, chapter_number),
        "retrieved_sources": _retrieved_sources_for_prompt(profile, chapter_number),
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "chapter_specific_requirements": _chapter_specific_requirements(chapter_number),
        "output_requirements": [
            "Write in formal British English.",
            "Use the selected academic level internally to determine depth and sophistication, but never mention the selected level in the generated chapter text.",
            "Use an evidence-to-paragraph method: each substantive paragraph should have a purpose, a claim grounded in supplied evidence or source-bank material, interpretation, and a clear link to the objective or chapter argument.",
            "Where the user has supplied limited information, write a focused draft with red bracketed placeholders asking for the exact missing facts, data, citations, institutional details, result tables, or supervisor decisions.",
            "Do not write sentences that say the work, chapter, section, depth, or argument is designed to meet the selected level of the project, thesis, or dissertation.",
            "Use the reference_currency_requirements: aim for at least 70% of substantive references within the stated recent-reference window.",
            "Use the citation_and_evidence_requirements: include relevant, accurate in-text citations across all substantive write-up sections.",
            "Every chapter must end with a References section that includes complete reference entries for every source cited in the chapter.",
            "Do not fabricate citations, statistics, or reference-list entries.",
            "Use clear numbered headings matching the selected sections.",
            "Draft only the selected sections.",
            "Write as a completed academic project, dissertation, or thesis. Avoid proposal-style future tense across the write-up, except where Chapter Five legitimately suggests future research using 'should', 'could', or 'may'.",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "Use APA 7th style for the chapter References section.",
            "For Chapter One, make the Background and Statement of the Problem factual and evidence-led.",
            "For Chapter Three, use past tense for completed project work.",
            "For Chapter Four, transform supplied result files and answers into a clean thesis chapter. Do not write phrases such as 'the uploaded results'.",
            "For Chapter Four, report only results found in uploaded files or student answers. Do not fabricate numbers, tables, themes, or interpretation.",
            "For Chapter Five, base conclusions and recommendations only on findings supplied in the profile or answers.",
        ],
    }
    return json.dumps(prompt, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# LIGHT HUMANISATION (only safe, non‑mechanical transformations)
# ----------------------------------------------------------------------

def _body_and_reference_tail(text: str) -> tuple[str, str]:
    """Separate chapter body from References/Source Use Audit."""
    if not text:
        return "", ""
    match = re.search(r"(?im)^#{0,3}\s*(references|source\s+use\s+audit)\b", text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip(), text[match.start():].lstrip()


def _looks_like_protected_block(paragraph: str) -> bool:
    """Return True for blocks that must not be rewritten (tables, headings, references, etc.)."""
    stripped = (paragraph or "").strip()
    if not stripped:
        return True
    protected_prefixes = ("#", "|", "```", "$$", "<table", "<tr", "<td")
    if stripped.startswith(protected_prefixes):
        return True
    if re.match(r"^\s*[-*+]\s+", stripped):
        return True
    if re.match(r"^\s*\d+[.)]\s+", stripped):
        return True
    if "http://" in stripped or "https://" in stripped or "doi.org" in stripped:
        return True
    if "[insert " in stripped.lower() and len(stripped.split()) < 30:
        return True
    return False


def _map_prose_paragraphs(text: str, func) -> str:
    """Apply a function only to prose paragraphs, preserving protected blocks."""
    parts = re.split(r"(\n\s*\n)", text or "")
    out: list[str] = []
    for part in parts:
        if re.match(r"\n\s*\n", part or ""):
            out.append(part)
            continue
        if _looks_like_protected_block(part):
            out.append(part)
            continue
        try:
            out.append(func(part))
        except Exception:
            out.append(part)
    return "".join(out)


def _remove_ai_transition_words(text: str) -> str:
    """Replace obvious AI transition words with simpler alternatives."""
    replacements = {
        r"\bFurthermore\b": "Also",
        r"\bMoreover\b": "Also",
        r"\bIn addition\b": "Additionally",
        r"\bConsequently\b": "As a result",
        r"\bIt is important to note that\b": "",
        r"\bIt is worth noting that\b": "",
        r"\bIt should be noted that\b": "",
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def _cluster_citations(text: str) -> str:
    """Combine adjacent parenthetical citations that are already present."""
    if not text:
        return text
    def combine(m: re.Match) -> str:
        first = m.group(1).strip("()")
        second = m.group(2).strip("()")
        if "[" in first+second or "insert" in (first+second).lower():
            return m.group(0)
        if first == second:
            return f"({first})"
        return f"({first}; {second})"
    pattern = r"(\([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?\))\s*(?:;|,|and)?\s*(\([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?\))"
    return re.sub(pattern, combine, text)


def _add_occasional_short_sentence(text: str) -> str:
    """
    Very occasionally (once per ~600 words) insert a short, natural punch sentence.
    No forced regularity. The phrases are varied and placed in a random sentence position.
    """
    words = text.split()
    if len(words) < 500:
        return text
    # Only run with low probability
    if random.random() > 0.25:
        return text

    # Find a suitable paragraph (not too short, not too long)
    paragraphs = re.split(r"(\n\s*\n)", text)
    prose_paras = [p for p in paragraphs if not re.match(r"\n\s*\n", p or "") and not _looks_like_protected_block(p) and len(p.split()) > 50]
    if not prose_paras:
        return text

    para = random.choice(prose_paras)
    sentences = re.split(r"(?<=[.!?])\s+", para)
    if len(sentences) < 2:
        return text

    # Choose a random sentence position (not first, not last)
    pos = random.randint(1, len(sentences)-1)
    short_phrases = [
        "That matters.", "This is not accidental.", "Consider that.", 
        "The implication is not trivial.", "Yet this pattern is not universal.",
        "A closer look suggests otherwise.", "This observation is key."
    ]
    short = random.choice(short_phrases)
    sentences.insert(pos, short)
    new_para = " ".join(sentences)

    # Replace the original paragraph
    idx = paragraphs.index(para)
    paragraphs[idx] = new_para
    return "".join(paragraphs)


def _vary_paragraph_openings(text: str) -> str:
    """If two consecutive prose paragraphs start with the same word, prepend a light transition."""
    paragraphs = re.split(r"(\n\s*\n)", text or "")
    transitions = ["Yet, ", "Still, ", "In this respect, ", "At the same time, ", "More specifically, "]
    prev_start = ""
    out = []
    for para in paragraphs:
        if re.match(r"\n\s*\n", para or "") or _looks_like_protected_block(para):
            out.append(para)
            continue
        words = para.strip().split()
        curr = words[0].lower() if words else ""
        if curr and curr == prev_start and not para.lstrip().startswith(tuple(transitions)) and random.random() < 0.3:
            para = random.choice(transitions) + para.strip()
        prev_start = curr
        out.append(para)
    return "".join(out)


def _apply_light_humanisation(text: str) -> str:
    """Apply only safe, non‑mechanical transformations to prose."""
    if not text:
        return text
    body, tail = _body_and_reference_tail(text)
    if not body.strip():
        return text

    body = _remove_ai_transition_words(body)
    body = _cluster_citations(body)
    body = _add_occasional_short_sentence(body)
    body = _vary_paragraph_openings(body)

    # Final polish to remove any leftover meta‑phrases
    body = _polish_generated_text(body)
    return body.rstrip() + ("\n\n" + tail if tail else "")


def _polish_generated_text(text: str) -> str:
    """Lightly remove common proposal/meta phrases that weaken scholarly output."""
    if not text:
        return text
    replacements = {
        r"\bThe research problem is that\b": "The central concern is that",
        r"\bthe research problem is that\b": "the central concern is that",
        r"\bThis is done to meet the level of the project\b": "",
        r"\bThis is done to meet the level of the thesis\b": "",
        r"\bThis is done to meet the level of the dissertation\b": "",
        r"\bto meet the selected academic level\b": "",
        r"\bto satisfy the selected academic level\b": "",
        r"\bfor the selected academic level\b": "",
        r"\bwill be used\b": "was used",
        r"\bwill be adopted\b": "was adopted",
        r"\bwill be employed\b": "was employed",
        r"\bwill be collected\b": "were collected",
        r"\bwill be analysed\b": "were analysed",
        r"\bwill be analyzed\b": "were analysed",
        r"\bwill be conducted\b": "was conducted",
        r"\bwill be administered\b": "was administered",
        r"\bwill be obtained\b": "was obtained",
        r"\bwill use\b": "used",
        r"\bwill adopt\b": "adopted",
        r"\bwill employ\b": "employed",
        r"\bwill collect\b": "collected",
        r"\bwill analyse\b": "analysed",
        r"\bwill analyze\b": "analysed",
        r"\bwill administer\b": "administered",
        r"\bwill examine\b": "examined",
        r"\bwill assess\b": "assessed",
        r"\bwill investigate\b": "investigated",
        r"\bwill determine\b": "determined",
        r"\bthe uploaded results show\b": "the results show",
        r"\bthe uploaded output shows\b": "the results show",
        r"\bthe output uploaded shows\b": "the results show",
        r"\bthe attached results show\b": "the results show",
        r"\bin today's world\b": "in the present context",
        r"\bit is important to note that\b": "",
        r"\bdelve into\b": "examine",
        r"\bplays a crucial role\b": "is important",
        r"\bvarious factors\b": "specific factors",
        r"\bit is imperative\b": "it is necessary",
        r"\bfrom the uploaded results\b": "from the results",
        r"\bfrom the uploaded output\b": "from the results",
        r"\bfrom the attached output\b": "from the results",
        r"\buploaded results\b": "results",
        r"\buploaded output\b": "results",
    }
    polished = text
    for pattern, repl in replacements.items():
        polished = re.sub(pattern, repl, polished, flags=re.IGNORECASE)
    polished = re.sub(r"(?im)^.*(?:selected academic level|level of the project|level of the thesis|level of the dissertation|checklist requirement|template requirement|software requirement).*\n?", "", polished)
    polished = re.sub(r"[ \t]{2,}", " ", polished)
    polished = re.sub(r"\n{3,}", "\n\n", polished)
    return polished.strip()


# ----------------------------------------------------------------------
# MAIN GENERATION FUNCTION (DeepSeek only, light humanisation)
# ----------------------------------------------------------------------

def generate_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    use_ai: bool = True,
) -> tuple[str, str]:
    """
    Generate a chapter using only DeepSeek, then apply light humanisation.
    """
    if not use_ai:
        return (
            _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)),
            "local_fallback_ai_disabled",
        )

    try:
        base_prompt = build_drafting_prompt(profile, chapter_number, selected_section_ids, answers, extra_instructions)
    except Exception:
        return (
            _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)),
            "local_fallback_prompt_error",
        )

    thesis_system = (
        "You are a human-supervised academic thesis drafting assistant. "
        "Write thesis-standard, evidence-led, formal British English. "
        "Use supplied/retrieved references actively, with author-year in-text citations and an APA-style References section. "
        "Do not cite irrelevant sources and do not invent sources, statistics, ethical approvals, sample sizes, results or reference details. "
        "Where evidence is missing, insert a precise bracketed placeholder. "
        "Vary sentence length, paragraph shape, and transitions naturally. "
        "Do not add AI-detection, humanisation, provider, model or internal-process notes."
    )

    draft_prompt = json.dumps(
        {
            "task": "Draft the full thesis chapter now.",
            "chapter_number": chapter_number,
            "base_drafting_prompt": base_prompt,
        },
        ensure_ascii=False,
        indent=2,
    )

    # Generate draft with a moderate temperature for natural variation
    draft = _call_deepseek(draft_prompt, thesis_system, temperature=0.75, max_tokens=12000)
    if not draft:
        return (
            _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)),
            "deepseek_failed",
        )

    final_text = _polish_generated_text(draft)
    # Apply only light, safe humanisation (no aggressive burstiness or rare words)
    final_text = _apply_light_humanisation(final_text)
    return final_text, "deepseek_light_humanised"


# ----------------------------------------------------------------------
# FALLBACK CHAPTER GENERATION (local template)
# ----------------------------------------------------------------------

def generate_fallback_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
) -> str:
    chapter = get_chapter(chapter_number)
    effective_chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}
    title = profile.get("title", "[Project Title]")
    lines = [f"# CHAPTER {chapter_number}", f"# {effective_chapter_title.upper()}", "", f"Study title: {title}", ""]
    for idx, section in enumerate(sections, 1):
        section_title = section["section_title"]
        section_answers = answers.get(section["section_id"], {})
        lines.append(f"## {chapter_number}.{idx} {section_title}")
        lines.append("")
        if section["section_id"] == "ch2_gap_table":
            lines.append(_fallback_literature_gap_table(section_answers, profile))
        elif chapter_number == 4 and section["section_id"] in {"ch4_uploaded_results", "ch4_results_objectives"}:
            lines.append(_fallback_results_section(section_answers, profile, chapter_number))
        elif section_answers:
            lines.append(_draft_from_answers(section_title, section.get("rules", []), section_answers, profile, chapter_number))
        else:
            lines.append(_placeholder_paragraph(section_title, section.get("rules", []), profile, chapter_number))
        lines.append("")
    return "\n".join(lines).strip()


def _draft_from_answers(
    section_title: str,
    rules: list[str],
    section_answers: dict[str, Any],
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    joined = []
    for k, v in section_answers.items():
        if isinstance(v, list):
            v = "; ".join(str(x) for x in v if str(x).strip())
        if str(v).strip():
            joined.append(f"{k}: {v}")
    answer_text = " ".join(joined)
    if not answer_text:
        return _placeholder_paragraph(section_title, rules, profile, chapter_number)
    rules_text = " ".join(rules[:3])
    if chapter_number == 3:
        return (
            f"The methodological choices in this section were shaped by the following study details: {answer_text}. "
            f"The section should be refined into a fully evidenced account of the procedures actually used, including dates, instruments, approvals, and verified methodological citations where required. "
            f"The discussion should remain aligned with these expectations: {rules_text}."
        )
    return (
        f"The section should be developed from the following study details: {answer_text}. "
        f"The discussion should connect these details to the study problem, objectives, context, and evidence base, while addressing these expectations: {rules_text}. "
        f"Where a claim requires support, insert accurate in-text citations, verified recent evidence, or relevant statistics rather than unsupported assertions."
    )


def _placeholder_paragraph(section_title: str, rules: list[str], profile: dict[str, Any], chapter_number: int) -> str:
    title = profile.get("title", "the study")
    requirements = " ".join(rules[:4]) if rules else "Follow the selected institutional requirements."
    if chapter_number == 3:
        return (
            f"This section requires the project-specific methodological details that were actually used in {title}. "
            f"The account should remain in past tense and should cover these methodological expectations: {requirements} "
            f"[insert study-specific methods, approvals, evidence, and citations here]."
        )
    return (
        f"This section requires further project-specific detail for {title}. "
        f"The discussion should be evidence-led and should address these expectations: {requirements} "
        f"[provide study-specific details, accurate evidence, statistics where relevant, and verified in-text citations here]."
    )


def _fallback_literature_gap_table(section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    objectives = profile.get("objectives") or profile.get("specific_objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    if not objectives:
        objectives = ["[insert research objective 1]", "[insert research objective 2]"]
    rows = ["| Research Objective | Key Authors and Year | Context of Study | Method Used | Key Findings | Identified Gap | Relevance to Current Study |", "|---|---|---|---|---|---|---|"]
    for obj in objectives:
        rows.append(f"| {obj} | [insert author and year] | [insert study context] | [insert method] | [insert key finding] | [insert objective-specific gap] | [explain relevance to the present study] |")
    return "\n".join(rows)


def _fallback_results_section(section_answers: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    uploaded = _uploaded_results_for_chapter(profile, chapter_number)
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    if not objectives:
        objectives = ["[insert research objective 1]", "[insert research objective 2]"]
    lines = []
    extracted = str((uploaded or {}).get("extracted_text") or (uploaded or {}).get("preview") or "").strip()
    if extracted:
        lines.append("The chapter should convert the supplied analysis evidence into clean academic results tables and interpretation. Do not mention the file upload in the final prose.")
        lines.append("\n**Available analysis evidence for drafting use only:**\n")
        lines.append(extracted[:2200])
    else:
        lines.append("The results required for this section were not supplied. The chapter should contain placeholder tables in red bracketed text and should tell the user exactly which analysis output is needed.")
    lines.append("\n**Objective-to-results table:**\n")
    lines.append("| Research Objective | Required Analysis/Table | Result to Report | Interpretation | Required Action if Missing |")
    lines.append("|---|---|---|---|---|")
    for obj in objectives:
        lines.append(f"| {obj} | [insert analysis method] | [insert statistic/coefficient/theme/result] | [insert interpretation] | [obtain the exact software/output table needed for this objective] |")
    lines.append("\n**Suggested missing-results placeholders:**\n")
    lines.append("| Required Table/Figure | Purpose | Placeholder | User Action |")
    lines.append("|---|---|---|---|")
    lines.append("| Response rate or data profile | Establish final sample/dataset | [insert final sample, usable responses, response rate or dataset period] | Provide response summary or dataset description |")
    lines.append("| Descriptive statistics | Summarise variables/constructs | [insert means, standard deviations, frequencies or theme counts] | Provide descriptive output |")
    lines.append("| Main analysis table | Answer objectives/hypotheses | [insert coefficients, p-values, path estimates, themes or comparison statistics] | Provide regression/SEM/econometric/qualitative output |")
    lines.append("| Figure or diagram | Visualise key results/model | [insert Figure: results chart/path diagram/conceptual model here] | Provide chart, model output or diagram data |")
    if section_answers:
        joined = []
        for k, v in section_answers.items():
            if str(v).strip():
                joined.append(f"{k}: {v}")
        if joined:
            lines.append("\n**Student guidance supplied:** " + " ".join(joined))
    return "\n\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return blocks
