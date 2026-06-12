from __future__ import annotations

import json
import os
import re
import random
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from app.template_store import get_chapter, selected_sections

load_dotenv()


def _safe_get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None



def _reference_currency_requirements() -> dict[str, Any]:
    """Return the reference currency rule used across generated chapters."""
    current_year = datetime.now().year
    start_year = current_year - 5
    return {
        "current_year": current_year,
        "recent_reference_window": f"{start_year}-{current_year}",
        "rule": (
            f"Aim for at least 70% of substantive references to be from {start_year}-{current_year}. "
            "Where current references do not exist for a specific concept, method, context, or theory, use the strongest credible available sources. "
            "Older sources are acceptable for foundational theories, classic models, scarce-literature areas, and essential earlier studies."
        ),
        "integrity_guard": (
            "Do not fabricate citations or reference-list entries. Use sources supplied by the student or sources that can be stated with confidence. "
            "If no credible source details are available, insert a clear bracketed placeholder such as "
            f"[insert verified recent source if available, {start_year}-{current_year}] or [insert credible available source]."
        ),
    }


def _citation_and_evidence_requirements(chapter_number: int) -> dict[str, Any]:
    """Return rules for evidence-led writing, citation accuracy, and problem-statement statistics."""
    current_year = datetime.now().year
    start_year = current_year - 5
    common_rules = [
        "Include relevant and accurate in-text citations in every substantive section of the write-up.",
        "Use author-year citation style unless the user or institution requests another style.",
        "Do not cite a source unless the source was supplied by the student, included in the profile/reference notes, present in uploaded material, or can be stated confidently without guessing.",
        "Where a citation is needed but no reliable source details are available, insert a red bracketed placeholder in the draft, such as [insert verified source for this claim] rather than inventing a citation.",
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
    """Return writing-depth guidance based on the selected thesis/dissertation/project level."""
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
    """Merge latest retrieved sources and accumulated source bank without replacing user evidence."""
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
    for idx, src in enumerate(collected, start=1):
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


def _source_attention_target(chapter_number: int, source_count: int) -> int:
    if source_count <= 0:
        return 0
    if chapter_number == 2:
        return min(source_count, 10)
    if chapter_number == 1:
        return min(source_count, 6)
    if chapter_number == 3:
        return min(source_count, 4)
    if chapter_number == 4:
        return min(source_count, 5)
    return min(source_count, 3)


def _relevance_tier_rank(tier: Any) -> int:
    return {"highly_relevant": 3, "partly_relevant": 2, "not_relevant": 1}.get(str(tier or ""), 0)


def _source_relevance_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"highly_relevant": 0, "partly_relevant": 0, "not_relevant": 0, "unclassified": 0}
    for src in sources:
        tier = str(src.get("relevance_tier") or "unclassified")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _retrieved_sources_for_prompt(profile: dict[str, Any], chapter_number: int | None = None) -> dict[str, Any]:
    """Return source-search results in a compact prompt-friendly form."""
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
    compact_sources.sort(
        key=lambda item: (
            _relevance_tier_rank(item.get("relevance_tier")),
            bool(item.get("abstract")),
            bool(item.get("doi")),
        ),
        reverse=True,
    )
    target = _source_attention_target(int(chapter_number or 0), len(compact_sources))
    return {
        "query": retrieved.get("query", ""),
        "searched_at": retrieved.get("searched_at", ""),
        "recent_reference_window": retrieved.get("recent_reference_window", ""),
        "databases": retrieved.get("databases", []),
        "usage_note": retrieved.get("usage_note", ""),
        "source_count": len(compact_sources),
        "relevance_counts": _source_relevance_counts(compact_sources),
        "recommended_relevant_sources_to_review": target,
        "sources": compact_sources,
        "source_use_rules": [
            "Use retrieved_sources as an additional evidence bank alongside the student's project profile, pasted verified evidence, uploaded files, and placeholders.",
            "Do not replace student-supplied evidence with search results; enrich the existing argument only where a retrieved source is directly relevant.",
            f"Use the recommended_relevant_sources_to_review value ({target}) only as a review guide, not as a compulsory citation quota.",
            "Prioritise sources marked highly_relevant, then partly_relevant. Use not_relevant sources only if a human has confirmed their relevance in the project notes.",
            "Apply a relevance gate before every citation: cite a retrieved source only when its title, abstract, method, context, theory, or finding directly supports the sentence or paragraph being written.",
            "Do not cite irrelevant, weakly related, or merely keyword-matching sources. It is better to use a placeholder than to cite an unsuitable source.",
            "Do not list retrieved sources in the References section unless they were actually cited in the chapter body.",
            "Use the supplied in_text_citation value for author-year citations where possible.",
            "Use the supplied reference_entry_hint when building the References section for sources actually cited.",
            "Where retrieved sources are insufficient for a claim, use a bracketed placeholder rather than inventing or forcing a citation.",
            "If any source search results are attached, end the chapter with a short Source Use Audit after the References section. The audit should list cited sources and relevant-but-not-cited sources with reasons. It should also state that irrelevant sources were excluded.",
            "Do not invent page numbers, quotations, findings, or reference-list details not present in the metadata or supplied by the student.",
            "Introduce controlled stylistic asymmetries: occasionally allow an analytical sentence to end with a preposition or a slightly awkward, dense noun-adjunct if it reflects natural human drafting friction.",
            "Break uniform topical flow by inserting localized, highly specific empirical exceptions or messy real-world counter-examples mid-argument, rather than smoothly transitioning from point to point.",
            "Avoid mathematical paragraph balancing. Force the system to follow a long, three-sentence complex clause immediately with a blunt, single-sentence conceptual anchor.",
            "Deliberately suppress the use of high-probability academic pairings (e.g., if the model wants to write 'intricately linked', force it to use 'tied together' or 'interact directly').",
            "Inject micro-level cognitive backtracking, where a sentence subtly re-evaluates or restricts the scope of the assertion made in the immediately preceding sentence, mimicking a student correcting their own draft's overreach."

        ],
    }

def _human_scholarly_style_requirements(seed: Optional[int] = None) -> dict[str, list[str]]:
    """
    Returns a high‑standard, randomly sampled set of humanising rules.
    Non‑deterministic application prevents repetitive AI patterns.
    """
    if seed is not None:
        random.seed(seed)

    full_rules = {
        "syntactic_burstiness": [
            "Vary sentence length with target std dev 12–18 words (mean ~20). Never use uniform lengths for >3 consecutive sentences.",
            "Insert at least one very short sentence (3–7 words) every 100–150 words. Use it to deliver a conceptual punch or blunt concession.",
            "Every 2–3 paragraphs, write one deliberately over‑nested sentence (4+ clauses) followed immediately by a terse rephrasing (e.g., 'Or, more simply: X.')",
            "Avoid the three‑part parallel structure (e.g., 'First, X. Second, Y. Third, Z.') more than once per 500 words.",
            "When listing evidence, vary formats: run‑in lists, dashed interruptions, parenthetical asides, occasionally no list marker."
        ],
        "argumentative_authenticity": [
            "Inject a genuine doubt or counterargument in every section except conclusion. Frame as 'One might object that...' then rebut.",
            "Never write a paragraph that only summarises a source. Always append an interpretive sentence: extends, limits, compares, or applies to your own problem.",
            "Introduce one 'self‑interruption' per 800 words: a sentence beginning with 'But wait –' or 'That said, a closer look reveals...'",
            "Do not resolve every tension immediately. Let one theoretical or empirical contradiction persist across 2–3 paragraphs.",
            "Use hedging that varies in strength: 'strongly suggests', 'weakly implies', 'raises the possibility that' depending on evidence."
        ],
        "lexical_vernacular": [
            "Replace LLM‑favoured bridge phrases ('furthermore', 'moreover', 'in addition', 'consequently') with domain‑specific connectors: 'This holds only if', 'By the same logic', 'A corollary is...'.",
            "Forbidden tokens (zero tolerance): 'delve', 'testament', 'tapestry', 'landscape' (as noun for domain), 'crucial' (use 'central', 'necessary'), 'imperative' (except Kant), 'it is important to note'.",
            "Prefer concrete, image‑evoking verbs where field‑appropriate: 'splits', 'bridges', 'collapses', 'shifts'. For formal fields: 'differentiates', 'juxtaposes', 'transposes'.",
            "Every 300 words, introduce one mildly idiosyncratic but correct phrase – e.g., 'stubborn assumption', 'generous sample size'."
        ],
        "citation_and_evidence": [
            "Cluster citations to show conceptual mapping: (e.g., Smith 2019; Jones 2020 on tension, but see Lee 2021 for counterview). Never pure parenthetical list without commentary.",
            "Vary citation density: sometimes one citation per claim; other times 3–6 citations at end of complex sentence to signal well‑established area.",
            "Use narrative citations with present‑perfect for ongoing debates: 'Smith has argued...' interspersed with simple past for settled findings.",
            "Deliberately include one 'I find X, yet Y suggests the opposite' pattern per literature review subsection."
        ],
        "local_incoherence_and_repair": [
            "Every 400–600 words, write a sentence that is slightly over‑specified or meandering (extra clause). In the next sentence, explicitly repair with 'To put it more clearly:' or 'What I mean is:'.",
            "Introduce one false start per 1000 words – a sentence beginning with a wrong direction, then a dash and correction. Example: 'The model predicts – or rather, it does not predict, but accommodates – the anomaly.'",
            "Use a footnote or parenthetical remark that is slightly too conversational, e.g., '(a point often missed in the rush to quantification)'."
        ],
        "token_biome": [
            "Maintain 3‑gram and 4‑gram overlap with human academic corpora. Avoid the same trigram (e.g., 'in order to', 'the fact that') more than twice per page.",
            "Never start two consecutive paragraphs with the same part‑of‑speech pattern (e.g., both starting with a prepositional phrase).",
            "Randomly alternate between that‑clauses and gerund phrases for stating claims: 'We argue that X' vs. 'Arguing for X requires...'.",
            "Use contractions sparingly but not never: one or two per 2000 words (e.g., 'doesn’t', 'it’s') in less formal sections (footnotes, concluding remarks)."
        ]
    }

    # Randomly sample ~70% of rules from each category to avoid deterministic application
    selected_rules = []
    for cat, rules in full_rules.items():
        n = max(1, int(len(rules) * 0.7))
        selected_rules.extend(random.sample(rules, n))

    # Return in the original structure expected by build_drafting_prompt
    return {"humanizer_rules": selected_rules}


def _student_contribution_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    """Return user-supplied human contribution and writing-style controls.

    These controls are designed to improve academic quality and specificity.
    They are not detector-evasion instructions. The model should use them to build
    a supervised, evidence-led draft from the student's own inputs.
    """
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
        "paragraph_development_protocol": [
            "Before writing each substantive paragraph, identify the paragraph purpose, the evidence or user input available, the interpretation required, and the link to the study objective.",
            "Use the student's project-specific context, evidence anchors, supervisor comments, and preferred style wherever supplied.",
            "If the user has not supplied enough evidence for a confident claim, use a clear red bracketed placeholder instead of writing a generic unsupported claim.",
            "Avoid over-polished, perfectly balanced, template-like prose. Use natural scholarly reasoning, varied sentence structure, and context-specific transitions.",
            "Apply controlled high-burstiness and extremely high-perplexity academic style in practical terms: vary rhythm, vocabulary, sentence openings, and paragraph shape while preserving clarity, evidence, and disciplinary precision.",
            "Where a writing sample is supplied, use it only to infer broad tone, sentence rhythm and level of directness; do not copy wording or imitate personal details.",
            "Make the draft sound like it has passed through a careful supervisor-student revision process: specific, cautious, evidenced and reflective, not generic or promotional.",
            "Do not add a visible AI-detection or humanisation note to the chapter; the chapter should read as an ordinary academic draft.",
        ],
        "generic_language_to_avoid": [
            "in today's world", "it is important to note", "delve into", "plays a crucial role",
            "various factors", "significant impact used vaguely", "this highlights the importance",
            "this study aims to contribute used vaguely", "moreover repeated mechanically",
            "furthermore repeated mechanically", "the research problem is that",
        ],
    }

def _chapter_specific_requirements(chapter_number: int) -> list[str]:
    """Return chapter-level drafting rules that apply beyond section rules."""
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
            "For conceptual framework sections, do not create messy ASCII diagrams. Present a clean relationship table and, where a diagram is needed, provide a simple Mermaid flowchart code block that can be rendered later.",
            "Explain the conceptual framework in prose after the table or diagram, including independent, dependent, mediating, moderating and control variables where applicable.",
        ]

    if chapter_number == 3:
        return common + [
            "Write Chapter Three as a completed final project, dissertation, or thesis chapter, not as a proposal.",
            "Use past tense and completed-study wording throughout Chapter Three, for example: 'the study adopted', 'data were collected', 'respondents were selected', 'the questionnaire was administered', and 'the data were analysed'.",
            "Do not use proposal-style future tense such as 'will adopt', 'will collect', 'will be used', 'will be analysed', 'will be administered', 'will be obtained', or 'will be conducted'.",
            "If a detail has not been supplied, use a past-tense placeholder, for example '[insert sampling procedure used]' or '[insert data collection period]', not future-tense wording.",
            "Maintain consistency among philosophy, approach, design, sampling, instrument, validity, reliability, analysis, and ethics.",
            "The methodology chapter should follow a strong doctoral-methods structure: introduction, research philosophy, research approach, study design, target population, sample size and sampling procedure, operationalisation and measurement, sources of data, data collection instrument, reliability and validity, ethical considerations, and data processing and analysis.",
            "For primary survey studies, include common method variance and social desirability safeguards, including procedural remedies such as varied scale formats, careful item ordering, anonymity, and statistical checks where applicable.",
            "Use a variable or construct operationalisation table where measurement is discussed, with columns: Variable/Concept, Indicator/Dimension, Operational Indicator, Item Scale, Level of Measurement, and Origin/Source.",
            "Use an analysis-plan table where data analysis is discussed, with columns: Research Objective, Research Question/Hypothesis, Analytical Technique, Ex-Ante Assumptions, Post-Estimation/Analysis Checks, and Decision Rule.",
            "When model equations are needed, present each equation in a separate display equation block using double dollar delimiters. Prefer clean Word-friendly mathematical notation using Unicode Greek letters and subscripts where possible, for example SDᵢ = β₀ + β₁PCRᵢ + ∑ₖ₌₁ᵐ βₖCVₖᵢ + εᵢ. Define all variables directly below the equation.",
        ]

    if chapter_number == 4:
        return common + [
            "Write a clean Results/Data Analysis and Discussion chapter. Do not refer to the file as 'uploaded results', 'the uploaded output', 'the output uploaded', or similar; convert the supplied output into normal thesis prose and tables.",
            "Study any supplied results, statistical output, qualitative coding output, Excel tables, SPSS/Stata/R output, or analysis notes and reorganise them into a coherent chapter aligned with the methods and objectives.",
            "Create all required tables that match the research methods, objectives, questions and hypotheses: response/profile table, descriptive statistics, reliability/validity where applicable, assumptions/diagnostics, objective-by-objective results, model estimates/path coefficients/regression/econometric tables, qualitative theme tables, and hypothesis decision tables where relevant.",
            "Use only results actually supplied in uploaded files or student answers. Do not invent coefficients, p-values, sample sizes, reliability values, model fit statistics, themes, quotations or percentages.",
            "Where a required result is missing, create a clean placeholder table with bracketed red placeholders such as [insert regression coefficients and p-values here] and add a short advisory sentence telling the user the exact result/output to obtain.",
            "Where a figure, graph, conceptual/path diagram or visual result is required but missing, insert a red placeholder such as [insert Figure 4.1: Conceptual/path diagram or chart here] and state the output needed to create it.",
            "Advise what should go to appendix, including raw software output, long diagnostics, full correlation matrices, full interview transcripts, questionnaires, codebooks and lengthy robustness checks. Keep the main text clean.",
            "Map each result to the relevant research objective, question or hypothesis before discussing it.",
            "Interpret results beyond description and link discussion to theory, prior studies and context using relevant citations.",
        ]

    if chapter_number == 5:
        return common + [
            "Base summaries, conclusions, recommendations, and future research suggestions only on supplied findings.",
            "Ensure each recommendation can be traced to a finding.",
        ]

    if chapter_number == 6:
        return common + [
            "Treat this as a user-specified additional chapter. Use the user's requested headings, scope and evidence requirements as the organising structure.",
            "Do not force standard Chapter One to Chapter Five content into this custom chapter unless the user requests it.",
            "Keep the chapter aligned with the overall project title, objectives, theory, method, results and recommendations.",
        ]

    if chapter_number == 7:
        return [
            "Treat this as a Supplementary Methods Chapter, not the main Research Methods/Methodology chapter. It is a working/support document for gathering analysis inputs, developing instruments, tracing measurement/data sources, preparing coding notes and organising appendix materials.",
            "Do not rewrite or replace the submission-ready Research Methods/Methodology chapter. Keep the distinction clear in the generated text.",
            "For primary survey or mixed-method studies, include objective-to-construct alignment, instrument development and source traceability, draft questionnaire, draft interview guide where applicable, validation notes and appendix placement guide.",
            "For secondary data, econometrics, time-series or panel-data studies, include a variable/data-source register, operational definition table, preferred data source placeholders, transformation/coding notes, quality checks and appendix guidance.",
            "Use the project source bank where available for questionnaire scales, validated item sources, operational definitions and data-source traceability. Cite only relevant sources.",
            "Where a questionnaire scale, validated item source, data source, period, frequency, code, transformation, permission note or validation output is missing, insert a red bracketed placeholder such as [insert verified scale source for this construct] or [insert verified data source and access link].",
            "Create clean, complete tables for alignment, source traceability, questionnaire items, interview themes, variable/data-source register, coding/transformation notes, quality checks and appendix placement where relevant.",
            "Include an APA-style References section containing only sources cited in the supplementary chapter.",
        ]

    return common



def _effective_chapter_title(chapter: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    """Return the chapter title used in prompts and fallback drafts.

    The dropdown uses standard names such as Introduction and Others. When the user
    selects Others and supplies a custom title, the generated chapter should use the
    user's title while the menu still shows Others.
    """
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
        section_payload.append(
            {
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "guiding_questions": section.get("guiding_questions", []),
                "rules": section.get("rules", []),
                "student_answers": answers.get(section["section_id"], {}),
            }
        )

    prompt = {
        "task": "Draft a full academic project chapter using selected institutional guideline sections.",
        "chapter": {
            "chapter_number": chapter_number,
            "chapter_title": effective_chapter_title,
        },
        "project_profile": profile,
        "selected_academic_level_and_depth": _level_depth_requirements(profile),
        "reference_currency_requirements": _reference_currency_requirements(),
        "citation_and_evidence_requirements": _citation_and_evidence_requirements(chapter_number),
        "human_scholarly_style_requirements": _human_scholarly_style_requirements(seed=hash(profile.get("title", "")) & 0xFFFFFFFF),
        "student_contribution_and_style_controls": _student_contribution_requirements(profile),
        "analysis_evidence_for_this_chapter": _uploaded_results_for_chapter(profile, chapter_number),
        "retrieved_sources": _retrieved_sources_for_prompt(profile, chapter_number),
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "chapter_specific_requirements": _chapter_specific_requirements(chapter_number),
        "output_requirements": [
            "Write in formal British English.",
            "Use the selected academic level internally to determine depth and sophistication, but never mention the selected level in the generated chapter text.",
            "Follow the human_scholarly_style_requirements and student_contribution_and_style_controls so the writing sounds natural, rigorous, context-specific, evidence-led and carefully supervised rather than generic or mechanical.",
            "In all generated chapters, use controlled high-burstiness and extremely high-perplexity scholarly writing: natural variation in sentence length, paragraph shape, vocabulary, transitions and argumentative movement, without sacrificing clarity, evidence, APA accuracy or methodological precision.",
            "Use the student's central argument, local context notes, evidence anchors, supervisor comments, preferred writing style and supplied writing sample as style/context guidance; do not copy the writing sample verbatim unless the user has written it as content to include.",
            "Use an evidence-to-paragraph method: each substantive paragraph should have a purpose, a claim grounded in supplied evidence or source-bank material, interpretation, and a clear link to the objective or chapter argument.",
            "Before producing a long paragraph, ask internally whether the user supplied enough context, evidence or source support for that paragraph. If not, write a shorter defensible paragraph and insert a precise red placeholder for the missing evidence.",
            "Make the writing high-quality and human-supervised by adding discipline-specific reasoning, careful qualifications, context-specific transitions and clear links between evidence and the student's own objectives.",
            "Where the user has supplied limited information, avoid creating long polished generic prose. Write a focused draft with red bracketed placeholders asking for the exact missing facts, data, citations, institutional details, result tables, or supervisor decisions.",
            "Respect the selected draft maturity: a structured draft can be more schematic; a supervisor-ready or revised academic draft must be more developed, but still grounded in user-supplied evidence and sources.",
            "Avoid very short sentences except where they are necessary for emphasis, transition, or clarity.",
            "Do not write sentences that say the work, chapter, section, depth, or argument is designed to meet the selected level of the project, thesis, or dissertation.",
            "Use the reference_currency_requirements: aim for at least 70% of substantive references within the stated recent-reference window, but where current sources do not exist, use the strongest credible available sources instead.",
            "Use the citation_and_evidence_requirements: include relevant, accurate in-text citations across all substantive write-up sections, especially literature, methodology justification, discussion, and problem framing.",
            "Use retrieved_sources as an additional evidence bank where the user has run the source finder. Do not replace the project profile, user-provided evidence, uploaded files, or placeholders; enrich the draft with relevant retrieved sources.",
            "When retrieved_sources contains sources marked highly_relevant or partly_relevant, review them carefully and integrate those that directly support the chapter argument. Do not cite not_relevant sources, and do not cite any source merely to increase citation count.",
            "Every chapter must end with a References section that includes complete reference entries for every source cited in the chapter, using available reference_entry_hint/apa_hint details from the source bank and user-supplied evidence notes. If source search results were attached, add a short Source Use Audit after the References section.",
            "Increase in-text citation density: Chapter Two should be citation-rich; Chapter One should cite evidence for context, problem and gaps; Chapter Three should cite methodological authorities where appropriate; Chapter Four discussion should cite theory and prior studies.",
            "If retrieved_sources do not provide enough support for a required claim, insert a bracketed placeholder such as [insert verified source for this claim] rather than guessing.",
            "For Chapter One, make the Background and Statement of the Problem factual and evidence-led. Use relevant accurate statistics, policy evidence, institutional evidence, or empirical findings to support the problem where supplied or confidently known.",
            "Do not fabricate citations, statistics, or reference-list entries. Use verified/supplied citations and facts where available. Where a required source, statistic, or fact is not supplied or cannot be stated confidently, insert a bracketed placeholder rather than inventing it.",
            "Use clear numbered headings matching the selected sections.",
            "Draft only the selected sections.",
            "Use analytical and connective prose: show why each point matters to the study rather than merely naming concepts, authors, variables, or methods.",
            "Avoid weak or unscholarly problem-statement phrasing such as 'The research problem is that...'. Use an evidence-led academic formulation instead.",
            "Write as a completed academic project, dissertation, or thesis. Avoid proposal-style future tense across the write-up, except where Chapter Five legitimately suggests future research using 'should', 'could', or 'may'.",
            "Prefer precise, discipline-appropriate wording over exaggerated claims or promotional language.",
            "Do not invent fabricated references, statistics, ethical approvals, sample sizes, or data results.",
            "Where evidence is missing, write a bracketed placeholder such as [insert recent empirical evidence].",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "Use markdown tables only where a table is clearly requested or useful.",
            "Use APA 7th style for the chapter References section. Include only sources cited in the chapter body, and keep entries clean, complete and alphabetised where possible.",
            "When equations are required, place each equation in a display equation block using the format $$ equation $$. Use clean Word-friendly mathematical notation where possible, with Unicode Greek letters and subscripts rather than raw LaTeX commands. Do not leave important equations only as ordinary text.",
            "For conceptual framework diagrams, avoid messy ASCII art. Use a clean relationship table and, where appropriate, a Mermaid flowchart code block. Keep the diagram simple enough to be readable.",
            "When revision mode is enabled, preserve the original structure as far as possible, revise with comments in the narrative where helpful, and wrap new inserted material in [[ADD]] and [[/ADD]] markers so the DOCX export can colour additions red.",
            "For Chapter Two tables, use a properly structured markdown table with meaningful column headers and one idea per cell.",
            "For Chapter Three, use past tense for completed project work and avoid future-tense proposal wording.",
            "For Chapter Four, transform supplied result files and answers into a clean thesis chapter. Do not write phrases such as 'the uploaded results', 'uploaded output', 'the output uploaded', or 'the attached file shows'. Present the tables and narrative as normal Results/Data Analysis and Discussion content.",
            "For Chapter Four, create the tables required by the selected methodology and objectives. If a required table cannot be completed from the supplied results, create a placeholder markdown table with red bracketed placeholders and advise the user exactly which output to obtain.",
            "For Chapter Four, insert red placeholders for required missing figures, graphs, path diagrams, conceptual diagrams or charts, and advise whether they belong in the main chapter or appendix.",
            "For Chapter Four, advise which materials should move to appendices, such as raw software output, lengthy diagnostic tables, full correlation matrices, full questionnaires, interview transcripts, codebooks and robustness checks.",
            "For Chapter Four, report only results found in uploaded files or student answers. Do not fabricate numbers, tables, themes, or interpretation.",
            "For the Research Methods/Methodology chapter, produce a complete, clean, submission-ready methodology chapter. Do not present it as a planning note, upload summary, worksheet, or supplementary file.",
            "For questionnaire or interview-guide outputs, build draft instruments from the constructs, variables and objectives supplied in the project profile rather than giving only a generic structure.",
            "Keep a clear distinction between the main Research Methods/Methodology chapter and the Supplementary Methods Chapter. The main methodology chapter is the clean submission-ready chapter; the supplementary chapter is a separate support document for instruments, data sources, scale traceability, coding, validation checks and appendix materials.",
            "Do not overload the main Research Methods/Methodology chapter with a full questionnaire, interview guide, scale bank, secondary-data register, or data-source codebook. Those details belong in the separate Supplementary Methods Chapter or appendix unless the institution specifically requires them in the main chapter.",
            "For Chapter Five, base conclusions and recommendations only on findings supplied in the profile or answers.",
        ],
    }
    return json.dumps(prompt, ensure_ascii=False, indent=2)

def _increase_natural_variation(text: str) -> str:
    """Post‑process to improve sentence length std dev and break repetitive trigrams."""
    if not text:
        return text

    # 1. Split into sentences (simple heuristic)
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    if len(sentences) < 4:
        return text

    # 2. Ensure at least one very short sentence (3–7 words) in the first 200 characters
    first_200 = text[:200]
    if not re.search(r'(?<![A-Z][a-z]\.)[.!?]\s+\b\w{1,4}\b', first_200):
        # Insert a short clarifying sentence after the first period.
        match = re.search(r'([^.?!]+[.!?])\s+', first_200)
        if match:
            short_clause = " That is, it matters. "
            text = text[:match.end()] + short_clause + text[match.end():]

    # 3. Replace common trigrams with natural alternatives
    trigram_replacements = {
        r'\bin order to\b': 'to',
        r'\bthe fact that\b': 'that',
        r'\bas well as\b': 'and also',
        r'\bdue to the fact that\b': 'because',
        r'\bit is important to note that\b': '',
        r'\bas a result of\b': 'from',
    }
    for pattern, repl in trigram_replacements.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # 4. Occasionally join two short consecutive sentences (increase burstiness)
    short_pair = re.search(r'([^.?!]{5,20}[.!?])\s+([^.?!]{5,20}[.!?])', text)
    if short_pair and random.random() < 0.3:
        joined = short_pair.group(1).rstrip('.!?') + ', and ' + short_pair.group(2).lstrip()
        text = text[:short_pair.start()] + joined + text[short_pair.end():]

    return text

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
    for pattern, replacement in replacements.items():
        polished = re.sub(pattern, replacement, polished, flags=re.IGNORECASE)

    # Remove full sentences that explicitly disclose internal level/template/checklist guidance.
    polished = re.sub(
        r"(?im)^.*(?:selected academic level|level of the project|level of the thesis|level of the dissertation|checklist requirement|template requirement|software requirement).*\n?",
        "",
        polished,
    )

    polished = re.sub(r"[ \t]{2,}", " ", polished)
    polished = re.sub(r"\n{3,}", "\n\n", polished)
    return polished.strip()



def _source_usage_count(text: str, sources: list[dict[str, Any]]) -> int:
    """Count how many retrieved source-bank records appear to be cited in the chapter body."""
    if not text or not sources:
        return 0
    body = text
    refs_match = re.search(r"(?im)^#{0,3}\s*references\b", text)
    if refs_match:
        body = text[: refs_match.start()]
    used = 0
    lower_body = body.lower()
    for src in sources:
        year = str(src.get("year") or "").strip()
        authors = src.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        family_names = [_normalise_author_for_citation(a).lower() for a in authors if str(a).strip()]
        family_names = [f for f in family_names if f and f != "[author]"]
        if not family_names:
            continue
        first = re.escape(family_names[0])
        year_ok = bool(year and year != "n.d." and re.search(re.escape(str(year)), body))
        author_ok = bool(re.search(first, lower_body))
        if author_ok and (year_ok or len(family_names) == 1):
            used += 1
    return used


def _source_reference_hints(sources: list[dict[str, Any]]) -> str:
    lines = []
    for src in sources:
        hint = src.get("apa_hint") or src.get("reference_entry_hint") or ""
        citation = _citation_label_for_source(src)
        title = src.get("title", "")
        if hint:
            lines.append(f"- {src.get('citation_key', '')} {citation}: {hint}")
        elif title:
            lines.append(f"- {src.get('citation_key', '')} {citation}: {title}")
    return "\n".join(lines)



def _has_source_use_audit(text: str) -> bool:
    return bool(re.search(r"(?im)^#{0,3}\s*source\s+use\s+audit\b", text or ""))


def _relevant_source_bank(profile: dict[str, Any]) -> list[dict[str, Any]]:
    sources = _merged_source_bank(profile)
    relevant = [s for s in sources if str(s.get("relevance_tier") or "").lower() in {"highly_relevant", "partly_relevant", "unclassified"}]
    relevant.sort(key=lambda item: _relevance_tier_rank(item.get("relevance_tier")), reverse=True)
    return relevant

def _review_source_integration(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    """Run a single relevance-gated review pass for attached source results.

    This pass does not force citations. It asks the model to use clearly relevant
    searched sources where they genuinely strengthen the chapter, and to add a
    Source Use Audit explaining why sources were cited or excluded.
    """
    source_bank = _merged_source_bank(profile)
    if not source_bank:
        return draft

    relevant_sources = _relevant_source_bank(profile)
    used = _source_usage_count(draft, relevant_sources)
    has_audit = _has_source_use_audit(draft)

    # If the draft already used at least one relevant source and includes an audit,
    # do not keep revising. The audit lets a human judge whether non-use was defensible.
    if used > 0 and has_audit:
        return draft

    repair_payload = {
        "task": "Review the chapter draft against the attached source-search results using a relevance gate.",
        "chapter_number": chapter_number,
        "reason_for_review": (
            f"The attached source search returned {len(source_bank)} source records. About {used} relevant source-bank records appear to be cited in the body. "
            "Revise only where relevant searched sources genuinely support the chapter. Do not force unsuitable sources into the prose."
        ),
        "important_rules": [
            "Keep the student's project profile, uploaded results, supplied references, and placeholders; do not replace them.",
            "Use highly_relevant and partly_relevant source-bank records where they directly support a specific point, theory, method, context, empirical gap, or discussion.",
            "Do not cite sources marked not_relevant unless the student's own notes explicitly confirm their relevance.",
            "Do not cite a source unless it supports the specific sentence or paragraph being written.",
            "If no searched source fits a claim, keep or add a bracketed placeholder instead of forcing a citation.",
            "Increase citation density only where doing so improves scholarly support and accuracy.",
            "End the chapter with a References section for sources actually cited in the body.",
            "After the References section, add a short Source Use Audit with columns: Source Key, Relevance Tier, Decision, Reason.",
            "In the Source Use Audit, mark sources as Cited, Not cited - not relevant, or Not cited - not needed for this chapter.",
            "Do not invent new sources, statistics, page numbers, quotations, findings, or reference details.",
        ],
        "source_bank_reference_hints": _source_reference_hints(source_bank),
        "original_generation_prompt": original_prompt,
        "draft_to_revise": draft,
    }
    try:
        response = client.responses.create(
            model=model,
            instructions=(
                instructions
                + " Revise rather than restart. Preserve the student's context. Use only relevant attached sources and include a Source Use Audit."
            ),
            input=json.dumps(repair_payload, ensure_ascii=False, indent=2),
        )
        revised = getattr(response, "output_text", "").strip()
        if revised:
            return _polish_generated_text(revised)
    except Exception:
        return draft
    return draft



def _generic_language_score(text: str) -> int:
    patterns = [
        r"\bin today's world\b", r"\bit is important to note\b", r"\bdelve into\b",
        r"\bplays a crucial role\b", r"\bvarious factors\b", r"\bsignificant impact\b",
        r"\bthis highlights the importance\b", r"\bthis study aims to contribute\b",
        r"\bmoreover\b", r"\bfurthermore\b", r"\bthe research problem is that\b",
    ]
    lower = text or ""
    return sum(len(re.findall(pattern, lower, flags=re.IGNORECASE)) for pattern in patterns)

def _sentence_length_variance(text: str) -> float:
    """Return variance of sentence lengths (in words) as a simple measure of burstiness."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) < 2:
        return 0.0
    lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return variance
    
def _human_academic_revision_pass(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    """Run one quality-focused revision pass to increase natural variation and reduce generic prose."""
    controls = _student_contribution_requirements(profile)
    if not controls.get("human_revision_pass_requested", True):
        return draft

    has_user_context = any(str(controls.get(k) or "").strip() for k in [
        "central_argument", "local_context_notes", "evidence_anchors", "supervisor_comments", "preferred_style", "writing_sample", "phrases_to_avoid"
    ])

    current_variance = _sentence_length_variance(draft)

    revision_payload = {
        "task": "Revise the chapter for human‑supervised academic quality, specificity and natural scholarly flow.",
        "chapter_number": chapter_number,
        "draft_maturity": controls.get("draft_maturity"),
        "student_contribution_controls": controls,
        "current_sentence_length_variance": current_variance,
        "quality_rules": [
            "Revise rather than restart. Preserve the chapter structure, headings, accurate citations, tables, equations, placeholders and supplied results.",
            "Increase natural scholarly variation: vary sentence rhythm, paragraph density, transition choices, and analytical movement. Simulate a careful human editor, not a template.",
            "Break any three consecutive sentences that start with the same grammatical pattern (e.g., subject‑verb, 'The', 'This').",
            "Where you see two consecutive paragraphs beginning with the same phrase (e.g., 'Moreover,' 'In addition,'), rewrite one to use a causal or conditional opener.",
            "Add one deliberate 'self‑correction' per 800 words: a sentence that begins 'But wait –' or 'That said, a closer look reveals...' then qualifies the previous claim.",
            "Ensure at least one very short sentence (3–7 words) every 150 words. If missing, split a longer sentence or insert a concise anchor.",
            "Replace any 'furthermore', 'moreover', 'in addition' with domain‑specific logical connectors: 'This holds only if', 'By the same logic', 'A corollary is...'.",
            "Do not attempt to evade AI detectors and do not mention AI detection. The purpose is academic quality, specificity, and defensible student‑supervised writing.",
            "Remove generic filler, repetitive transitions, vague claims, inflated language, and over‑polished template‑like phrasing.",
            "Strengthen paragraph‑level reasoning: each paragraph should connect claim, evidence or placeholder, interpretation, and relevance to the study objective or chapter argument.",
            "Use the student's central argument, local context notes, evidence anchors, supervisor comments and preferred style where supplied.",
            "Where evidence is missing, keep or add red bracketed placeholders instead of inventing claims, statistics, results, ethical approvals, sources, sample sizes or institutional facts.",
            "Do not add a visible humanisation note, contribution log or detector note to the chapter body.",
            "Keep APA references complete and limited to sources cited in the chapter body.",
        ],
        "generic_language_score_before_revision": _generic_language_score(draft),
        "user_context_supplied": has_user_context,
        "original_generation_prompt": original_prompt,
        "draft_to_revise": draft,
    }
    try:
        response = client.responses.create(
            model=model,
            instructions=(
                instructions
                + " Perform one conservative academic‑quality revision pass. Do not restart the chapter. Do not add unsupported content."
            ),
            input=json.dumps(revision_payload, ensure_ascii=False, indent=2),
        )
        revised = getattr(response, "output_text", "").strip()
        if revised:
            return _polish_generated_text(revised)
    except Exception:
        return draft
    return draft



def _call_openai_response_safely(client: Any, model: str, instructions: str, prompt: str) -> str:
    """Call the OpenAI Responses API without allowing provider/API errors to crash the app.

    Render users were seeing generic Internal Server Error responses when the
    provider rejected a model name, timed out, or returned a transient error.
    This helper catches those errors so the route can return a local fallback
    rather than failing the request.
    """
    try:
        response = client.responses.create(model=model, instructions=instructions, input=prompt)
        return str(getattr(response, "output_text", "") or "").strip()
    except Exception:
        fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", "").strip()
        if fallback_model and fallback_model != model:
            try:
                response = client.responses.create(model=fallback_model, instructions=instructions, input=prompt)
                return str(getattr(response, "output_text", "") or "").strip()
            except Exception:
                return ""
        return ""

def generate_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    use_ai: bool = True,
) -> tuple[str, str]:
    """
    Generate a chapter using OpenAI (if available) or fallback to local templates.
    Incorporates high‑burstiness, randomise‑style humaniser and two revision passes.
    """
    try:
        prompt = build_drafting_prompt(profile, chapter_number, selected_section_ids, answers, extra_instructions)
    except Exception:
        # Fallback to local template if prompt construction fails
        return (
            _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)),
            "local_template_fallback_prompt_error"
        )

    client = _safe_get_openai_client()
    if use_ai and client:
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        instructions = (
            "You are ProjectReady AI, an academic project‑work drafting and compliance assistant. "
            "Write in a natural, high‑standard scholarly voice that sounds like a carefully supervised draft, "
            "built from the student's own evidence, context, supervisor comments and project decisions. "
            "Apply controlled high‑burstiness and high‑perplexity: vary sentence/paragraph length, transitions, vocabulary, "
            "and argumentative rhythm while keeping clarity, evidence‑led reasoning, and disciplinary precision. "
            "Never mention the selected academic level, template, or checklist. Avoid generic AI phrasing, filler, overclaiming, "
            "and perfectly balanced paragraphs. Use grounded verbs (suggests, indicates, complicates, qualifies). "
            "Do not begin problem statements with 'The research problem is that'. Frame problems through evidence, tension, or gap. "
            "Do not fabricate sources, results, approvals, or evidence. Use clear [bracketed placeholders] when information is missing. "
            "Write as a completed final project (past tense for methodology, future only for suggested research in Ch5). "
            "For Ch2: use clean markdown gap tables and Mermaid flowcharts for diagrams. For equations: display blocks with $$. "
            "For Ch4: never invent output; present only supplied results. Apply reference currency (≥70% recent, but allow older where needed). "
            "Include accurate in‑text citations. For source‑finder results: integrate only highly_relevant/partly_relevant records, "
            "exclude not_relevant, and add a Source Use Audit after References. Do not add any AI‑detection or humanisation notes – "
            "just produce normal scholarly prose."
        )

        text = _call_openai_response_safely(client, model, instructions, prompt)
        if text:
            # 1. Basic polish (phrase replacement, remove meta‑comments)
            polished = _polish_generated_text(text)

            # 2. Increase natural variation (short sentences, break trigrams, join pairs)
            polished = _increase_natural_variation(polished)

            # 3. Relevance‑gated source integration (adds Source Use Audit)
            polished = _review_source_integration(
                client=client,
                model=model,
                instructions=instructions,
                original_prompt=prompt,
                draft=polished,
                profile=profile,
                chapter_number=chapter_number,
            )

            # 4. Final human‑academic revision pass (improves burstiness, self‑correction)
            polished = _human_academic_revision_pass(
                client=client,
                model=model,
                instructions=instructions,
                original_prompt=prompt,
                draft=polished,
                profile=profile,
                chapter_number=chapter_number,
            )

            return polished, "openai_responses_api"

    # Fallback when AI is disabled or fails
    return (
        _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)),
        "local_template_fallback"
    )

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
    level_info = _level_depth_requirements(profile)
    ref_info = _reference_currency_requirements()
    lines = [
        f"# CHAPTER {chapter_number}",
        f"# {effective_chapter_title.upper()}",
        "",
        f"Study title: {title}",
        "",
    ]

    for index, section in enumerate(sections, 1):
        section_title = section["section_title"]
        section_answers = answers.get(section["section_id"], {})
        lines.append(f"## {chapter_number}.{index} {section_title}")
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
    joined_answers = []
    for key, value in section_answers.items():
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if str(v).strip())
        if str(value).strip():
            joined_answers.append(f"{key}: {value}")
    answer_text = " ".join(joined_answers)
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

    rows = [
        "| Research Objective | Key Authors and Year | Context of Study | Method Used | Key Findings | Identified Gap | Relevance to Current Study |",
        "|---|---|---|---|---|---|---|",
    ]
    for objective in objectives:
        rows.append(
            f"| {objective} | [insert author and year] | [insert study context] | [insert method] | [insert key finding] | [insert objective-specific gap] | [explain relevance to the present study] |"
        )
    return "\n".join(rows)



def _fallback_results_section(section_answers: dict[str, Any], profile: dict[str, Any], chapter_number: int) -> str:
    uploaded = _uploaded_results_for_chapter(profile, chapter_number)
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    if not objectives:
        objectives = ["[insert research objective 1]", "[insert research objective 2]"]

    lines: list[str] = []
    extracted = str((uploaded or {}).get("extracted_text") or (uploaded or {}).get("preview") or "").strip()
    if extracted:
        lines.append(
            "The chapter should convert the supplied analysis evidence into clean academic results tables and interpretation. "
            "Do not mention the file upload in the final prose; present the evidence as normal thesis results."
        )
        lines.append("\n**Available analysis evidence for drafting use only:**\n")
        lines.append(extracted[:2200])
    else:
        lines.append(
            "The results required for this section were not supplied. The chapter should contain placeholder tables in red bracketed text and should tell the user exactly which analysis output is needed."
        )

    lines.append("\n**Objective-to-results table:**\n")
    lines.append("| Research Objective | Required Analysis/Table | Result to Report | Interpretation | Required Action if Missing |")
    lines.append("|---|---|---|---|---|")
    for objective in objectives:
        lines.append(
            f"| {objective} | [insert analysis method aligned with methodology] | [insert statistic/coefficient/theme/result] | [insert interpretation linked to objective] | [obtain the exact software/output table needed for this objective] |"
        )

    lines.append("\n**Suggested missing-results placeholders:**\n")
    lines.append("| Required Table/Figure | Purpose | Placeholder | User Action |")
    lines.append("|---|---|---|---|")
    lines.append("| Response rate or data profile | Establish final sample/dataset | [insert final sample, usable responses, response rate or dataset period] | Provide response summary or dataset description |")
    lines.append("| Descriptive statistics | Summarise variables/constructs | [insert means, standard deviations, frequencies or theme counts] | Provide descriptive output |")
    lines.append("| Main analysis table | Answer objectives/hypotheses | [insert coefficients, p-values, path estimates, themes or comparison statistics] | Provide regression/SEM/econometric/qualitative output |")
    lines.append("| Figure or diagram | Visualise key results/model | [insert Figure: results chart/path diagram/conceptual model here] | Provide chart, model output or diagram data |")

    lines.append("\n**Appendix guidance:** raw software output, long diagnostic tables, full questionnaires, interview transcripts, full correlation matrices, detailed coding sheets and robustness checks should normally go to the appendix unless a supervisor requires them in the main text.")

    if section_answers:
        joined = []
        for key, value in section_answers.items():
            if str(value).strip():
                joined.append(f"{key}: {value}")
        if joined:
            lines.append("\n**Student guidance supplied:** " + " ".join(joined))

    return "\n\n".join(lines)

def split_paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return blocks
