from __future__ import annotations

import json
import os
import re
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
        timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "75"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
        return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=max_retries)
    except Exception:
        return None


def _extra_ai_passes_enabled(profile: dict[str, Any] | None = None) -> bool:
    """Return whether expensive multi-pass AI revision is enabled.

    The default is OFF because the Render request log showed a /draft request
    running for about 240 seconds. Running draft + source repair + human revision
    as three separate provider calls can exceed practical web-request limits.
    Human-quality and source-use instructions are now folded into the first call.
    Set PROJECTREADY_EXTRA_AI_PASSES=1 only for a larger instance or queued jobs.
    """
    env_value = os.getenv("PROJECTREADY_EXTRA_AI_PASSES", "0").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    try:
        controls = (profile or {}).get("student_contribution") or {}
        return bool(controls.get("enable_extra_ai_passes", False))
    except Exception:
        return False



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
        ],
    }

def _human_scholarly_style_requirements() -> list[str]:
    """Return high-standard academic writing rules for natural, polished chapter drafting."""
    return [
        "Use the selected academic level only as internal depth guidance. Do not mention the selected level, do not say the writing is produced to meet a level, and do not include meta-commentary about the project being written at a particular standard.",
        "Write in a mature, natural scholarly voice that resembles a carefully supervised student draft: precise, analytical, context-specific, and free from generic AI patterns.",
        "Use controlled high-burstiness academic prose: vary sentence length, paragraph length, transitions, and rhythm in a natural way, while keeping the argument clear, disciplined and defensible.",
        "Use high lexical and syntactic variety where it improves meaning: avoid flat, uniform, predictable sentence patterns, but do not make the writing obscure, inflated or artificially complicated.",
        "Do not make every paragraph look symmetrical. Some paragraphs may be compact and interpretive; others may be longer where evidence, methodological justification or theoretical explanation requires fuller development.",
        "Maintain scholarly clarity even when the prose is varied. Perplexity in this app means intellectually rich, context-specific and less formulaic writing; it does not mean confusing language, unsupported claims or unnecessary vocabulary.",
        "Avoid very short, clipped sentences except where a short sentence is needed for emphasis, transition, or clarity. Prefer well-developed academic sentences that connect evidence, reasoning, and implication.",
        "Vary sentence structure, but avoid overusing sentence frames such as 'This study...', 'The study...', 'The research problem is...', or 'This section...'.",
        "Do not begin a problem statement with wording such as 'The research problem is that...'. Frame the problem analytically, for example through a tension, contradiction, persistent gap, policy concern, empirical inconsistency, or unresolved practical challenge.",
        "Avoid mechanical, generic, and repetitive academic-AI phrasing such as 'in today's world', 'it is important to note', 'this study is very important', 'delve into', 'plays a crucial role', 'it is imperative', and repeated formulaic paragraph openings.",
        "Use a human academic rhythm: combine some concise analytical sentences with longer explanatory sentences, but never pad the text or make it artificially irregular.",
        "Show scholarly judgement by explaining why evidence matters, why alternatives were not selected, where a limitation exists, and how each point changes the reader's understanding of the study.",
        "Prefer grounded verbs such as suggests, indicates, implies, supports, complicates, qualifies and raises concern, instead of overconfident phrases such as proves, clearly shows or has a significant impact unless the evidence supports that claim.",
        "Avoid paragraph templates that repeatedly start with the same phrase. Use transitions that follow the logic of the argument rather than mechanical transitions.",
        "Do not merely list ideas. Build an argument by explaining relationships among concepts, comparing studies, identifying tensions, and showing why the present study is necessary.",
        "Every substantive paragraph should develop one clear idea through a topic sentence, evidence or reasoning, interpretation, and a closing implication linked to the study problem, objective, method, finding, or recommendation.",
        "Use critical synthesis rather than annotated-summary writing, especially in the literature review and discussion chapters.",
        "Integrate theory, empirical evidence, context, methodology, and findings in a way that sounds like a carefully supervised academic draft, not a template.",
        "Maintain discipline-appropriate terminology, but avoid unnecessary verbosity, inflated claims, and promotional language.",
        "Use signposting only where it helps the reader. Do not overuse headings or repeated introductory sentences.",
        "Write in third-person academic style unless the student's institution requires otherwise.",
        "Keep the work defensible: do not overstate contribution, causality, generalisability, or policy implications beyond the evidence supplied.",
    ]




def _student_contribution_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    """Return user-supplied human contribution and writing-style controls.

    These controls are designed to improve academic quality, specificity,
    evidence use and student-supervised revision.
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
            "Apply controlled high-burstiness and high-perplexity academic style in practical terms: vary rhythm, vocabulary, sentence openings, and paragraph shape while preserving clarity, evidence, and disciplinary precision.",
            "Where a writing sample is supplied, use it only to infer broad tone, sentence rhythm and level of directness; do not copy wording or imitate personal details.",
            "Make the draft sound like it has passed through a careful supervisor-student revision process: specific, cautious, evidenced and reflective, not generic or promotional.",
            "Do not add a visible writing-style note to the chapter; the chapter should read as an ordinary academic draft.",
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
        "human_scholarly_style_requirements": _human_scholarly_style_requirements(),
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
            "In all generated chapters, use controlled high-burstiness and high-perplexity scholarly writing: natural variation in sentence length, paragraph shape, vocabulary, transitions and argumentative movement, without sacrificing clarity, evidence, APA accuracy or methodological precision.",
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


def _human_academic_revision_pass(
    client: Any,
    model: str,
    instructions: str,
    original_prompt: str,
    draft: str,
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    """Run one quality-focused revision pass to reduce generic prose.

    This is an academic-quality pass, not a detector-evasion pass. It asks the model
    to make the writing more context-specific, evidence-led and supervisor-ready while
    preserving citations, data, placeholders and chapter structure.
    """
    controls = _student_contribution_requirements(profile)
    if not controls.get("human_revision_pass_requested", True):
        return draft

    has_user_context = any(str(controls.get(k) or "").strip() for k in [
        "central_argument", "local_context_notes", "evidence_anchors", "supervisor_comments", "preferred_style", "writing_sample", "phrases_to_avoid"
    ])
    # Always run the pass for AI-generated drafts, but keep it short and conservative.
    revision_payload = {
        "task": "Revise the chapter for human-supervised academic quality, specificity and natural scholarly flow.",
        "chapter_number": chapter_number,
        "draft_maturity": controls.get("draft_maturity"),
        "student_contribution_controls": controls,
        "quality_rules": [
            "Revise rather than restart. Preserve the chapter structure, headings, accurate citations, tables, equations, placeholders and supplied results.",
            "The purpose is academic quality, specificity, and defensible student-supervised writing.",
            "Remove generic filler, repetitive transitions, vague claims, inflated language, and over-polished template-like phrasing.",
            "Increase natural scholarly variation: vary sentence rhythm, paragraph density, transition choices and analytical movement so the prose reads like careful human academic editing rather than uniform template output.",
            "Strengthen paragraph-level reasoning: each paragraph should connect claim, evidence or placeholder, interpretation, and relevance to the study objective or chapter argument.",
            "Use the student's central argument, local context notes, evidence anchors, supervisor comments and preferred style where supplied.",
            "Where evidence is missing, keep or add red bracketed placeholders instead of inventing claims, statistics, results, ethical approvals, sources, sample sizes or institutional facts.",
            "Do not add a visible style note or contribution log to the chapter body.",
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
                + " Perform one conservative academic-quality revision pass. Do not restart the chapter. Do not add unsupported content."
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

    The call is intentionally bounded so a web request does not hang for several
    minutes. If the provider is slow, unavailable, or rejects the configured model,
    the app returns an explicit local draft instead of an Internal Server Error.
    """
    max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "6500"))
    create_kwargs = {
        "model": model,
        "instructions": instructions,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    try:
        response = client.responses.create(**create_kwargs)
        return str(getattr(response, "output_text", "") or "").strip()
    except TypeError:
        # Older SDKs may not support max_output_tokens on responses.create.
        try:
            response = client.responses.create(model=model, instructions=instructions, input=prompt)
            return str(getattr(response, "output_text", "") or "").strip()
        except Exception:
            pass
    except Exception:
        pass

    fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", "").strip()
    if fallback_model and fallback_model != model:
        try:
            create_kwargs["model"] = fallback_model
            response = client.responses.create(**create_kwargs)
            return str(getattr(response, "output_text", "") or "").strip()
        except TypeError:
            try:
                response = client.responses.create(model=fallback_model, instructions=instructions, input=prompt)
                return str(getattr(response, "output_text", "") or "").strip()
            except Exception:
                return ""
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
    try:
        prompt = build_drafting_prompt(profile, chapter_number, selected_section_ids, answers, extra_instructions)
    except Exception:
        return _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)), "local_template_fallback_prompt_error"
    client = _safe_get_openai_client()
    if use_ai and client:
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        instructions = (
            "You are ProjectReady AI, an academic project-work drafting and compliance assistant. "
            "You help students draft chapters from selected guidelines. You support learning and compliance. "
            "Write in a natural, high-standard scholarly voice that sounds like a carefully supervised academic draft built from the student's own evidence, context, supervisor comments and project decisions, not generic AI prose. The writing should show judgement, local specificity, cautious interpretation and paragraph-level reasoning. "
            "In every generated output, apply controlled high-burstiness and high-perplexity academic style: vary sentence length, paragraph shape, transitions, vocabulary and argumentative rhythm, while keeping the writing clear, evidence-led, disciplined and suitable for thesis or dissertation work. "
            "Use the selected academic level only to determine depth; never mention the selected level or say the chapter is written to meet a level, checklist, template, or software requirement. "
            "Avoid generic AI-style phrasing, repetition, filler, overclaiming, template-like prose, and very short choppy sentences except where a short sentence is needed for clarity. "
            "Build coherent academic arguments with critical synthesis, contextual relevance, and defensible reasoning. Use paragraph-level judgement rather than formulaic section filling, and avoid perfectly repetitive sentence patterns or generic balanced paragraphs. "
            "Do not begin the problem statement with phrases such as 'The research problem is that'; frame the problem through evidence, contradiction, gap, policy concern, or unresolved practical challenge. "
            "You do not fabricate sources, results, approvals, page numbers, or evidence. "
            "When the user has not provided facts, use clear placeholders rather than inventing content. "
            "Write as a completed final project, dissertation, or thesis. Avoid proposal-style future tense across chapters, especially Chapter Three methodology. "
            "For Chapter Two, format literature gap tables as clean markdown tables with clear columns. Avoid messy conceptual framework diagrams; use clean relationship tables and simple Mermaid flowcharts where a diagram is needed. "
            "For equations, use display equation blocks with double dollar delimiters and clean Word-friendly notation so the DOCX exporter can create readable Word equation objects. "
            "For Chapter Four, use uploaded results files where available and never invent analysis output. "
            "Complete source-use review, APA reference cleaning and human academic revision within this single response. Do not rely on a later revision pass. "
            "The prose should be naturally varied and context-specific, but it must remain academically clear, accurate and supervisor-ready rather than artificially complex. "
            "Let the selected thesis, dissertation, or project-work level guide depth silently without appearing in the chapter text. "
            "Make each section read like publishable or supervisor-ready academic prose, with a clear line of reasoning and strong paragraph development. "
            "Apply the reference currency rule: aim for most substantive citations to be from the last five years, but where recent literature does not exist, use credible available sources, including foundational theories and essential older studies. "
            "Include relevant and accurate in-text citations throughout the write-up. For the problem statement, use factual evidence and accurate statistics to show that the problem exists, where those facts are supplied or can be stated confidently. "
            "When source-finder results are available in the prompt, review them as an additional evidence bank. Integrate highly_relevant and partly_relevant records only where they directly support the argument; exclude not_relevant records. Add a Source Use Audit after the References section explaining which searched sources were cited or excluded. "
            "Do not fabricate citations, references, statistics, or institutional evidence. Use clear bracketed placeholders only when a credible source, fact, or statistic is not available or has not been supplied."
        )
        text = _call_openai_response_safely(client, model, instructions, prompt)
        if text:
            polished = _polish_generated_text(text)
            if _extra_ai_passes_enabled(profile):
                polished = _review_source_integration(
                    client=client,
                    model=model,
                    instructions=instructions,
                    original_prompt=prompt,
                    draft=polished,
                    profile=profile,
                    chapter_number=chapter_number,
                )
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

    return _polish_generated_text(generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers)), "local_template_fallback"



def generate_fallback_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
) -> str:
    """Create a usable thesis-standard local draft when the AI provider is unavailable.

    The earlier local fallback only repeated section rules and placeholders, which made the
    output look like a checklist rather than a chapter. This fallback now writes substantive,
    section-specific academic prose from the available title, context, objectives, variables,
    answers and source-bank hints. It still avoids fabricating statistics, results, ethical
    approvals or references; missing evidence is shown as precise bracketed placeholders.
    """
    chapter = get_chapter(chapter_number)
    effective_chapter_title = _effective_chapter_title(chapter, profile, chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}

    lines = [
        f"# {_chapter_heading_label(chapter_number)}",
        f"# {effective_chapter_title.upper()}",
        "",
    ]

    for index, section in enumerate(sections, 1):
        section_title = section["section_title"]
        section_answers = answers.get(section["section_id"], {})
        heading_number = _section_number(chapter_number, index)
        lines.append(f"## {heading_number} {section_title}")
        lines.append("")

        if chapter_number == 1:
            content = _fallback_chapter_one_section(section_title, section_answers, profile)
        elif chapter_number == 2:
            content = _fallback_chapter_two_section(section_title, section_answers, profile)
        elif chapter_number == 3:
            content = _fallback_methodology_section(section_title, section_answers, profile)
        elif chapter_number == 4:
            content = _fallback_results_section(section_answers, profile, chapter_number)
        elif chapter_number == 5:
            content = _fallback_chapter_five_section(section_title, section_answers, profile)
        elif chapter_number == 7:
            content = _fallback_supplementary_methods_section(section_title, section_answers, profile)
        elif section_answers:
            content = _draft_from_answers(section_title, section.get("rules", []), section_answers, profile, chapter_number)
        else:
            content = _substantive_placeholder_section(section_title, profile, chapter_number)

        lines.append(content.strip())
        lines.append("")

    if not re.search(r"(?im)^#{1,3}\s*references\b", "\n".join(lines)):
        refs = _fallback_references_section(profile)
        if refs:
            lines.append("## References")
            lines.append("")
            lines.append(refs)
            lines.append("")

    return "\n".join(lines).strip()


def _chapter_heading_label(chapter_number: int) -> str:
    labels = {1: "CHAPTER ONE", 2: "CHAPTER TWO", 3: "CHAPTER THREE", 4: "CHAPTER FOUR", 5: "CHAPTER FIVE", 6: "OTHERS", 7: "SUPPLEMENTARY METHODS CHAPTER"}
    return labels.get(int(chapter_number or 0), f"CHAPTER {chapter_number}")


def _section_number(chapter_number: int, index: int) -> str:
    if int(chapter_number or 0) == 7:
        return f"S{index}"
    return f"{chapter_number}.{index}"


def _profile_terms(profile: dict[str, Any]) -> dict[str, Any]:
    title = str(profile.get("title") or "the study").strip()
    context = str(profile.get("study_context") or "").strip()
    research_area = str(profile.get("research_area") or "").strip()
    data_type = str(profile.get("data_type") or "").strip()
    approach = str(profile.get("research_approach") or "").strip()

    objectives = profile.get("objectives") or profile.get("specific_objectives") or []
    if isinstance(objectives, str):
        objectives = [x.strip(" -•\t") for x in re.split(r"\n|;", objectives) if x.strip()]
    objectives = [str(x).strip() for x in objectives if str(x).strip()]

    questions = profile.get("research_questions") or []
    if isinstance(questions, str):
        questions = [x.strip(" -•\t") for x in re.split(r"\n|;", questions) if x.strip()]
    questions = [str(x).strip() for x in questions if str(x).strip()]

    variables = []
    raw_vars = profile.get("variables") or profile.get("constructs") or []
    if isinstance(raw_vars, dict):
        for key, value in raw_vars.items():
            if str(key).strip():
                variables.append(str(key).strip())
            if isinstance(value, str) and value.strip() and value.strip().lower() not in {str(key).strip().lower()}:
                variables.append(value.strip())
            elif isinstance(value, list):
                variables.extend(str(v).strip() for v in value if str(v).strip())
    elif isinstance(raw_vars, str):
        variables.extend(x.strip(" -•\t") for x in re.split(r"\n|;|,", raw_vars) if x.strip())
    elif isinstance(raw_vars, list):
        variables.extend(str(v).strip() for v in raw_vars if str(v).strip())

    # Try to infer variables from common title patterns.
    title_part = title
    title_part = re.split(r"\bamong\b|\bin\b|\bwithin\b|\busing\b", title_part, flags=re.IGNORECASE)[0]
    inferred = [x.strip(" .") for x in re.split(r"\band\b|,|:|;", title_part, flags=re.IGNORECASE) if len(x.strip()) > 3]
    for term in inferred[:4]:
        if term.lower() not in {v.lower() for v in variables}:
            variables.append(term)

    population = "the study population"
    m = re.search(r"among\s+(.+?)(?:\s+in\s+|\s+within\s+|$)", title, re.IGNORECASE)
    if m:
        population = m.group(1).strip(" .")
    location = "the study setting"
    m = re.search(r"\bin\s+(.+)$", title, re.IGNORECASE)
    if m:
        location = m.group(1).strip(" .")

    return {
        "title": title,
        "context": context or title,
        "research_area": research_area or "the research area",
        "data_type": data_type or "the selected data source",
        "approach": approach or "the selected research approach",
        "objectives": objectives,
        "questions": questions,
        "variables": _dedupe_keep_order(variables),
        "population": population,
        "location": location,
    }


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = re.sub(r"\s+", " ", str(item).strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(str(item).strip())
    return out


def _joined_variables(terms: dict[str, Any]) -> str:
    variables = terms.get("variables") or []
    if not variables:
        return "the core constructs of the study"
    if len(variables) == 1:
        return variables[0]
    return ", ".join(variables[:-1]) + " and " + variables[-1]


def _fallback_chapter_one_section(section_title: str, section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    title_lower = section_title.lower()
    evidence_note = _evidence_note(profile)
    answer_note = _answer_note(section_answers)

    if "introduction" in title_lower:
        return (
            f"This chapter introduces the study on {t['title']}. It situates the inquiry within {t['research_area']} and explains why {t['population']} in {t['location']} provide a meaningful context for examining {_joined_variables(t)}. "
            f"The chapter begins by setting out the background to the study, after which the problem is stated and narrowed into a clear research focus. It then presents the purpose of the study, research objectives, research questions, significance, delimitations, limitations and organisation of the study. "
            f"Together, these sections establish the intellectual and practical basis for the investigation and show how the study moves from a broad concern to a defined empirical inquiry. {answer_note}"
        )

    if "background" in title_lower:
        return (
            f"The preparation for later-life financial security has become a major personal finance and social policy concern, particularly in economies where many workers earn irregular income and operate outside formal employer-sponsored pension arrangements. Financial literacy is central to this concern because individuals need to understand saving, budgeting, risk, interest, inflation, pension participation and long-term financial planning before they can make informed retirement decisions. In informal work settings, however, these decisions are rarely made under stable conditions. Earnings may vary across seasons, business cycles and household demands, while access to structured financial advice and pension information may be limited. [insert recent empirical or policy source on financial literacy and retirement planning among informal workers].\n\n"
            f"The Ghanaian context adds a further layer to the issue. Informal workers contribute substantially to livelihoods and local economic activity, yet many do not benefit from the regular pension communication, payroll deductions and workplace financial education that formal employees may receive. For workers in {t['location']}, retirement planning is therefore likely to depend not only on knowledge of financial products but also on trust in pension institutions, income regularity, household obligations, business survival needs and access to appropriate financial services. [insert current Ghana Statistical Service, SSNIT, NPRA or Ministry of Employment evidence on informal employment and pension participation].\n\n"
            f"Conceptually, the study links {_joined_variables(t)} by treating financial literacy as more than the ability to recognise financial terms. It includes the capacity to interpret financial information and apply it to decisions about saving, investment, insurance, credit and retirement preparation. Retirement planning, in turn, refers to the deliberate actions taken to secure income, assets and welfare in old age. Where literacy is weak, retirement planning may be delayed, informal, inconsistent or shaped mainly by immediate household pressures rather than long-term income security.\n\n"
            f"Although financial literacy has received increasing attention in personal finance research, the specific circumstances of informal workers remain insufficiently understood in many local contexts. The present study therefore focuses on {t['population']} in {t['location']} to examine how financial knowledge, attitudes and practices relate to retirement preparation within a setting where income uncertainty and limited formal pension coverage may influence long-term financial behaviour. {evidence_note}"
        )

    if "problem" in title_lower:
        return (
            f"Many informal workers face the difficult task of preparing for retirement without the regular income, employer-based pension communication and structured financial counselling that often support formal sector employees. In such circumstances, retirement planning can easily be displaced by immediate business expenses, family obligations, debt servicing and daily consumption needs. This creates a practical problem: workers may remain economically active for many years but reach old age without adequate savings, pension participation or a clear plan for income security. [insert recent national or local evidence showing low pension participation, low savings, or weak retirement preparedness among informal workers].\n\n"
            f"The problem is not merely the absence of income. It also concerns the knowledge and confidence required to translate limited income into deliberate long-term planning. A worker may know the importance of saving but lack understanding of pension products; another may understand saving but distrust formal financial institutions; yet another may intend to plan for retirement but face income volatility that makes regular contributions difficult. These differences suggest that financial literacy may shape retirement planning in ways that are not captured by income level alone. [insert empirical source on financial literacy and retirement planning behaviour].\n\n"
            f"In {t['location']}, the issue is especially relevant because informal economic activities support many households, yet local evidence on how informal workers understand and practise retirement planning remains limited. Existing studies may address financial literacy broadly, pension participation nationally, or saving behaviour in general, but fewer studies appear to examine the specific relationship between financial literacy and retirement planning among {t['population']} in this local context. This study was therefore designed to examine {t['title']}, thereby providing evidence that can inform financial education, pension outreach and policy interventions for informal workers."
        )

    if "purpose" in title_lower:
        return (
            f"The purpose of the study was to examine {t['title']}. Specifically, the study sought to determine how financial literacy relates to retirement planning among {t['population']} in {t['location']} and to generate evidence that can support more effective financial education, pension communication and retirement-preparedness interventions for workers in the informal economy."
        )

    if "objective" in title_lower:
        objectives = t["objectives"] or [
            f"assess the level of financial literacy among {t['population']} in {t['location']}",
            f"assess the retirement planning practices of {t['population']} in {t['location']}",
            "examine the relationship between financial literacy and retirement planning",
            "identify the financial-literacy dimensions that most strongly explain retirement planning behaviour",
        ]
        lines = ["The study was guided by the following specific objectives:"]
        for i, obj in enumerate(objectives, 1):
            obj = obj.rstrip(".")
            if not re.match(r"(?i)^(to\s+)?(assess|examine|analyse|analyze|determine|evaluate|investigate|explore|identify|establish)", obj):
                obj = "examine " + obj
            if not obj.lower().startswith("to "):
                obj = "to " + obj
            lines.append(f"{i}. {obj};")
        lines[-1] = lines[-1].rstrip(";") + "."
        return "\n".join(lines)

    if "question" in title_lower:
        questions = t["questions"]
        if not questions:
            objectives = t["objectives"] or [
                f"assess the level of financial literacy among {t['population']} in {t['location']}",
                f"assess the retirement planning practices of {t['population']} in {t['location']}",
                "examine the relationship between financial literacy and retirement planning",
                "identify the financial-literacy dimensions that most strongly explain retirement planning behaviour",
            ]
            questions = [_objective_to_question(obj, t) for obj in objectives]
        lines = ["The study was guided by the following research questions:"]
        for i, q in enumerate(questions, 1):
            q = q.strip().rstrip("?") + "?"
            lines.append(f"{i}. {q}")
        return "\n".join(lines)

    if "significance" in title_lower:
        return (
            f"The study is significant to informal workers because it draws attention to the knowledge, attitudes and financial practices that may influence their preparedness for old age. Evidence from the study can help workers, trade associations and local business groups to recognise the importance of early and consistent retirement planning, even where income is irregular. It may also support the design of practical financial education programmes that speak directly to the realities of informal work rather than assuming salaried employment conditions.\n\n"
            f"The study is also useful to pension institutions, financial service providers and public agencies involved in financial inclusion. By showing how {t['population']} in {t['location']} understand and practise retirement planning, the findings can guide pension outreach, savings-product design, communication strategies and trust-building interventions. For policymakers, the study provides local evidence that can inform broader discussions on informal-sector social protection and old-age income security.\n\n"
            f"Academically, the study contributes to literature on financial literacy and retirement planning by focusing on a local informal-worker population. It extends the discussion beyond general financial knowledge by linking literacy to a concrete planning outcome and by situating the relationship within the economic realities of {t['location']}."
        )

    if "delimitation" in title_lower:
        return (
            f"The study was delimited to {t['population']} in {t['location']}. This boundary was necessary because the study sought to understand retirement planning within a specific informal-work context rather than across all categories of workers in Ghana. The study also focused on {_joined_variables(t)} and therefore did not examine all possible determinants of retirement security, such as health status, inheritance, family support, asset ownership or macroeconomic conditions, except where these issues were relevant to the interpretation of the findings."
        )

    if "limitation" in title_lower:
        return (
            f"The study was limited by its reliance on information provided by respondents about their financial knowledge and retirement planning practices. Such self-reported data may be affected by recall error or the tendency of respondents to present their financial behaviour more favourably. This limitation can be managed through clear questionnaire wording, anonymity and careful interpretation of the results.\n\n"
            f"Another limitation is that the study focuses on {t['location']}, which means that the findings may not automatically represent all informal workers in Ghana. Informal work varies across regions, occupations and income levels. The findings should therefore be interpreted within the selected study context, while future studies may extend the analysis to other municipalities, regions or occupational groups. [insert final methodological limitations after data collection and analysis]."
        )

    if "organisation" in title_lower or "organization" in title_lower:
        return (
            "The study is organised into five chapters. Chapter One introduces the study, presents the background, states the problem, outlines the purpose, objectives and research questions, and explains the significance, delimitations and limitations of the study. Chapter Two reviews relevant theoretical, conceptual and empirical literature and identifies the gap addressed by the study. Chapter Three describes the methodology, including the research approach, design, population, sampling, instrumentation, data collection procedures, validity, reliability, ethics and data analysis methods. Chapter Four presents and discusses the results in line with the research objectives. Chapter Five summarises the findings, draws conclusions, makes recommendations and suggests areas for future research."
        )

    return _substantive_placeholder_section(section_title, profile, 1)


def _objective_to_question(objective: str, terms: dict[str, Any]) -> str:
    text = re.sub(r"(?i)^to\s+", "", str(objective).strip()).rstrip(".")
    text = re.sub(r"(?i)^(assess|examine|analyse|analyze|determine|evaluate|investigate|explore|identify)\s+", "", text)
    if text.lower().startswith("the relationship"):
        return "What is " + text + f" among {terms['population']} in {terms['location']}"
    return "What is the nature of " + text


def _fallback_chapter_two_section(section_title: str, section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    lower = section_title.lower()
    if "gap table" in lower:
        return _fallback_literature_gap_table(section_answers, profile)
    if "introduction" in lower:
        return f"This chapter reviews literature relevant to {t['title']}. It examines the conceptual meaning of {_joined_variables(t)}, discusses relevant theoretical perspectives, reviews empirical studies, identifies gaps in existing literature and presents the conceptual framework guiding the study. The review is organised to maintain a direct connection between the research problem, the objectives and the eventual methodology."
    if "concept" in lower:
        return f"Conceptually, the study rests on {_joined_variables(t)}. Each concept should be defined in relation to the study context rather than treated as a dictionary term. The review should explain how the concepts are measured, how they interact, and why they matter for {t['population']} in {t['location']}. [insert verified conceptual and empirical sources for each construct]."
    if "theor" in lower:
        return f"The theoretical review should identify the theory or theories that explain why {_joined_variables(t)} are expected to relate in the manner proposed by the study. Each theory should be discussed in terms of its assumptions, relevance, limitations and specific application to {t['title']}. [insert appropriate foundational and recent theoretical sources]."
    if "empirical" in lower or "objective" in lower:
        return f"The empirical review should be organised by research objective. For each objective, discuss studies that are directly related to {t['title']}, indicating the context, sample, method, findings and limitations of each study. The review should not merely list previous studies; it should compare evidence, identify contradictions and show how the present study addresses a remaining gap in {t['location']} or among {t['population']}. [insert recent empirical studies, preferably 2021–2026, and older foundational studies where necessary]."
    if "framework" in lower:
        return _fallback_conceptual_framework(profile)
    return _substantive_placeholder_section(section_title, profile, 2)


def _fallback_methodology_section(section_title: str, section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    lower = section_title.lower()
    answer_note = _answer_note(section_answers)
    if "introduction" in lower:
        return f"This chapter describes the methods used to conduct the study on {t['title']}. It explains the philosophical position, research approach, design, population, sampling procedure, data collection instrument, validity and reliability procedures, ethical considerations and data analysis techniques. The purpose of the chapter is to show that the methodological choices were appropriate for answering the research questions and addressing the study objectives. {answer_note}"
    if "philosophy" in lower or "ontology" in lower or "epistemology" in lower:
        return f"The study was located within [insert philosophical paradigm used, such as positivism, interpretivism or pragmatism]. This position was appropriate because the inquiry required evidence on {t['title']} and sought to generate defensible conclusions from {t['data_type'].lower()}. The ontology, epistemology and methodological assumptions should be explained and linked directly to the study objectives rather than presented as abstract philosophical labels. [insert methodological source supporting the selected paradigm]."
    if "approach" in lower:
        return f"The study adopted a {t['approach'].lower()} approach. This approach was appropriate because the objectives required systematic evidence on {_joined_variables(t)} among {t['population']} in {t['location']}. The selected approach should be justified against alternative approaches, indicating why it provided the most suitable route for answering the research questions. [insert details of the final approach and supporting methodology citation]."
    if "design" in lower:
        return f"The study used [insert research design used, for example descriptive cross-sectional survey, correlational design, explanatory design, case study, panel design or time-series design]. The design was appropriate because it allowed the study to examine {t['title']} within the selected population and setting. The justification should show how the design aligned with the objectives, data type and analytical techniques."
    if "population" in lower:
        return f"The target population comprised {t['population']} in {t['location']}. The accessible population consisted of [insert accessible population and sampling frame]. The unit of analysis was [insert unit of analysis], because the study required data from the actors or records most directly connected to {_joined_variables(t)}."
    if "sample" in lower or "sampling" in lower:
        return f"The sample size was determined using [insert sample size determination method, formula or software]. The study used [insert sampling technique] because it was suitable for reaching {t['population']} in {t['location']} and for producing data aligned with the study objectives. The final methodology should state the population size, confidence level, margin of error, expected response rate and adjustment for non-response where applicable."
    if "operational" in lower or "measurement" in lower or "variable" in lower:
        return _fallback_operationalisation_table(profile)
    if "instrument" in lower:
        return f"Data were collected using [insert questionnaire/interview guide/documentary data sheet]. The instrument was structured around the study variables and objectives, ensuring that each section generated information needed for analysis. For primary survey work, the questionnaire should include respondent profile items, construct-specific items, scale anchors and ethical consent language. Detailed questionnaire items and scale-source traceability should be placed in the Supplementary Methods Chapter or appendix unless the school requires them in the main methodology chapter."
    if "valid" in lower or "reliab" in lower:
        return f"Validity was addressed through [insert content validity, expert review, pilot testing or construct validity procedure]. Reliability was assessed using [insert reliability method such as Cronbach's alpha, composite reliability, test-retest reliability or inter-coder agreement]. The specific thresholds and decision rules should be stated and justified with methodological sources."
    if "ethic" in lower:
        return "Ethical issues were addressed through informed consent, voluntary participation, confidentiality, anonymity and the responsible handling of data. Respondents were informed about the purpose of the study, their right to withdraw and the use of the data for academic purposes. [insert ethics approval number, institution, approval date or supervisor-approved ethics procedure if applicable]."
    if "analysis" in lower or "processing" in lower:
        return _fallback_analysis_plan_table(profile)
    return _substantive_placeholder_section(section_title, profile, 3)


def _fallback_chapter_five_section(section_title: str, section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    lower = section_title.lower()
    if "summary" in lower:
        return f"This section should summarise the study on {t['title']} by restating the purpose, approach and key findings in line with each research objective. The final version must use only the actual findings from Chapter Four. [insert objective-by-objective findings after results are finalised]."
    if "conclusion" in lower:
        return "The conclusions should be drawn directly from the findings and should answer the research questions without introducing new evidence. Each conclusion must be traceable to a specific finding in Chapter Four. [insert final conclusions after results are confirmed]."
    if "recommend" in lower:
        return "The recommendations should be practical, evidence-based and linked to the findings. Each recommendation should identify the relevant stakeholder, the action required and the reason for the recommendation. [insert recommendations only after findings are confirmed]."
    return _substantive_placeholder_section(section_title, profile, 5)


def _fallback_supplementary_methods_section(section_title: str, section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    lower = section_title.lower()
    if "alignment" in lower:
        return _fallback_objective_construct_alignment(profile)
    if "instrument" in lower or "questionnaire" in lower:
        return _fallback_questionnaire_table(profile)
    if "interview" in lower:
        return _fallback_interview_guide(profile)
    if "variable" in lower or "data source" in lower:
        return _fallback_data_source_register(profile)
    if "operational" in lower or "coding" in lower or "transformation" in lower:
        return _fallback_operationalisation_table(profile)
    if "quality" in lower or "validation" in lower or "reliability" in lower:
        return "This section should document the validation, reliability and data-quality checks required before analysis. For primary data, include expert review, pilot testing, reliability estimates and validity checks. For secondary data, include source reliability, missing-data checks, consistency checks, outlier inspection, transformation decisions and stationarity/diagnostic tests where applicable. [insert actual validation and quality-check outputs]."
    if "appendix" in lower:
        return "The appendix should contain the full questionnaire, interview guide, consent form, scale-source traceability table, detailed data-source notes, coding scheme, long diagnostic output, raw software output and any lengthy tables that would interrupt the flow of the main chapter."
    return _substantive_placeholder_section(section_title, profile, 7)


def _fallback_operationalisation_table(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    variables = t["variables"] or ["[insert variable/construct 1]", "[insert variable/construct 2]"]
    rows = [
        "The variables or constructs should be operationalised before data collection and analysis. A working structure is provided below and should be completed with validated sources or approved measurement decisions.",
        "",
        "| Variable/Concept | Dimension/Indicator | Operational Indicator | Item Scale/Measurement | Level of Measurement | Origin/Source |",
        "|---|---|---|---|---|---|",
    ]
    for variable in variables:
        rows.append(f"| {variable} | [insert dimension] | [insert operational indicator] | [insert scale/proxy] | [insert nominal/ordinal/interval/ratio] | [insert validated source or data source] |")
    return "\n".join(rows)


def _fallback_analysis_plan_table(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    objectives = t["objectives"] or ["[insert research objective 1]", "[insert research objective 2]"]
    rows = [
        "The analysis plan should link every objective to the exact technique, assumptions and decision rule to be applied.",
        "",
        "| Research Objective | Research Question/Hypothesis | Analytical Technique | Ex-Ante Assumptions | Post-Analysis Checks | Decision Rule |",
        "|---|---|---|---|---|---|",
    ]
    for obj in objectives:
        rows.append(f"| {obj} | [insert matching question/hypothesis] | [insert technique] | [insert assumptions] | [insert diagnostic/validity checks] | [insert decision rule] |")
    return "\n".join(rows)


def _fallback_objective_construct_alignment(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    objectives = t["objectives"] or ["[insert research objective 1]", "[insert research objective 2]"]
    variables = t["variables"] or ["[insert construct/variable]"]
    rows = [
        "| Research Objective | Construct/Variable Needed | Data Required | Instrument Section/Data Source | Analysis Link | Missing Information |",
        "|---|---|---|---|---|---|",
    ]
    for i, obj in enumerate(objectives):
        var = variables[i % len(variables)]
        rows.append(f"| {obj} | {var} | [insert data needed] | [insert questionnaire section/interview theme/data source] | [insert analysis technique] | [insert missing scale/source/result] |")
    return "\n".join(rows)


def _fallback_questionnaire_table(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    variables = t["variables"] or ["[insert construct]"]
    rows = [
        "The draft questionnaire should be developed from the approved constructs and objectives. The table below provides a construct-aligned item bank for review and refinement.",
        "",
        "| Section | Construct/Variable | Draft Item | Response Scale | Source/Adaptation Note |",
        "|---|---|---|---|---|",
        "| A | Respondent profile | [insert demographic/background item] | [insert response options] | Researcher-developed |",
    ]
    for idx, variable in enumerate(variables, 1):
        rows.append(f"| B{idx} | {variable} | [insert item measuring {variable}] | [insert Likert scale/proxy] | [insert verified scale source or indicate researcher-developed item] |")
        rows.append(f"| B{idx} | {variable} | [insert second item measuring {variable}] | [insert Likert scale/proxy] | [insert source/adaptation note] |")
    return "\n".join(rows)


def _fallback_interview_guide(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    variables = t["variables"] or ["[insert construct]"]
    lines = ["The interview guide should deepen the evidence obtained from the questionnaire or secondary data. Suggested prompts are provided below and should be revised to fit the final objectives.", ""]
    for variable in variables:
        lines.append(f"- How do participants understand {variable} in their own context?")
        lines.append(f"- What experiences or constraints shape {variable} among {t['population']} in {t['location']}?")
        lines.append(f"- What examples can participants provide to explain this issue?")
    return "\n".join(lines)


def _fallback_data_source_register(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    variables = t["variables"] or ["[insert variable]"]
    rows = [
        "| Variable | Preferred Data Source | Frequency/Period | Unit of Measurement | Transformation/Coding | Quality Check | Missing Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for variable in variables:
        rows.append(f"| {variable} | [insert verified data source] | [insert period/frequency] | [insert unit] | [insert transformation/coding] | [insert quality check] | [insert missing access link or definition] |")
    return "\n".join(rows)


def _fallback_conceptual_framework(profile: dict[str, Any]) -> str:
    t = _profile_terms(profile)
    variables = t["variables"] or ["Independent variable", "Dependent variable"]
    rows = [
        "The conceptual framework should show how the major constructs relate to one another and how the relationships connect to the study objectives.",
        "",
        "| Construct | Role in Framework | Expected Relationship | Justification/Source |",
        "|---|---|---|---|",
    ]
    for i, variable in enumerate(variables):
        role = "Independent/Explanatory variable" if i == 0 else "Dependent/Outcome variable" if i == 1 else "Control/Mediating/Additional variable"
        rows.append(f"| {variable} | {role} | [insert expected direction/relationship] | [insert theoretical or empirical support] |")
    rows.append("\n```mermaid\nflowchart LR\n    A[Independent construct] --> B[Outcome construct]\n    C[Control or contextual factors] --> B\n```")
    return "\n".join(rows)


def _substantive_placeholder_section(section_title: str, profile: dict[str, Any], chapter_number: int) -> str:
    t = _profile_terms(profile)
    return (
        f"This section should be developed as part of the { _effective_chapter_title(get_chapter(chapter_number), profile, chapter_number).lower() }. "
        f"For the present study on {t['title']}, the section should connect directly to the study objectives, the population of {t['population']}, and the context of {t['location']}. "
        f"The final version should include project-specific evidence, verified citations and any required institutional details. [insert section-specific evidence, citations or approved details for {section_title}]."
    )


def _answer_note(section_answers: dict[str, Any]) -> str:
    if not section_answers:
        return ""
    joined = []
    for key, value in section_answers.items():
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if str(v).strip())
        if str(value).strip():
            joined.append(f"{key}: {value}")
    return "Student-supplied detail: " + " ".join(joined) if joined else ""


def _evidence_note(profile: dict[str, Any]) -> str:
    notes = str(profile.get("citation_evidence_notes") or profile.get("notes") or "").strip()
    if not notes:
        return "[insert verified local statistics, policy evidence and empirical sources before final submission]."
    return f"The following supplied evidence should be incorporated and verified in the final draft: {notes[:900]}"


def _fallback_references_section(profile: dict[str, Any]) -> str:
    sources = _merged_source_bank(profile, limit=8)
    if not sources:
        return "[insert APA 7th reference entries for all sources cited in this chapter after verifying bibliographic details]."
    entries = []
    for src in sources:
        hint = str(src.get("apa_hint") or src.get("reference_entry_hint") or "").strip()
        if hint:
            entries.append(hint.rstrip("." ) + ".")
    return "\n".join(_dedupe_keep_order(entries)) if entries else "[insert APA 7th reference entries for all sources cited in this chapter after verifying bibliographic details]."


def _draft_from_answers(
    section_title: str,
    rules: list[str],
    section_answers: dict[str, Any],
    profile: dict[str, Any],
    chapter_number: int,
) -> str:
    answer_note = _answer_note(section_answers)
    t = _profile_terms(profile)
    if not answer_note:
        return _substantive_placeholder_section(section_title, profile, chapter_number)
    if chapter_number == 3:
        return (
            f"The methodological discussion for {section_title.lower()} was guided by the project-specific information supplied for {t['title']}. {answer_note} "
            "The final text should explain what was actually done, why it was appropriate, and how the decision aligned with the research objectives, data source and analysis plan. Where a methodological claim requires support, a verified methodological citation should be inserted."
        )
    return (
        f"For {section_title.lower()}, the discussion should develop the supplied information into coherent thesis prose. {answer_note} "
        f"The section should connect the information to {t['title']}, explain why it matters, and support substantive claims with verified evidence or precise placeholders where evidence is missing."
    )


def _placeholder_paragraph(section_title: str, rules: list[str], profile: dict[str, Any], chapter_number: int) -> str:
    return _substantive_placeholder_section(section_title, profile, chapter_number)


def _fallback_literature_gap_table(section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    objectives = _profile_terms(profile)["objectives"] or ["[insert research objective 1]", "[insert research objective 2]"]
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
    objectives = _profile_terms(profile)["objectives"] or ["[insert research objective 1]", "[insert research objective 2]"]
    lines: list[str] = []
    extracted = str((uploaded or {}).get("extracted_text") or (uploaded or {}).get("preview") or "").strip()
    if extracted:
        lines.append("The results are presented in line with the research objectives. The available analysis evidence should be converted into clean tables, concise interpretation and objective-by-objective discussion without referring to the file upload process.")
        lines.append("\n**Working evidence extracted for drafting use:**\n")
        lines.append(extracted[:2200])
    else:
        lines.append("The required analysis output was not supplied. The table below identifies the results that must be obtained before this section can be finalised.")
    lines.append("\n| Research Objective | Required Analysis/Table | Result to Report | Interpretation | Required Action if Missing |")
    lines.append("|---|---|---|---|---|")
    for objective in objectives:
        lines.append(f"| {objective} | [insert analysis aligned with methodology] | [insert statistic/coefficient/theme/result] | [insert interpretation linked to objective] | [obtain exact output required for this objective] |")
    lines.append("\n[insert Figure/Table placeholder in red where a chart, path diagram, model diagram or diagnostic plot is required]. Raw software output, lengthy diagnostics, full questionnaires, codebooks and full transcripts should normally be placed in the appendix.")
    return "\n".join(lines)
def split_paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return blocks
