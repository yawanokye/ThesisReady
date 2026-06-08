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


def _format_and_method_requirements(profile: dict[str, Any]) -> dict[str, Any]:
    """Return rules for institutional format flexibility and secondary/econometric work."""
    thesis_format = (profile.get("thesis_format") or "Standard five-chapter thesis/dissertation").strip()
    method_stream = (profile.get("method_stream") or profile.get("data_type") or profile.get("research_approach") or "Primary survey data").strip()
    format_notes = (profile.get("format_notes") or "").strip()

    rules = [
        "Treat the selected sections as the student's school-specific format. Draft only the selected headings and do not force unselected sections into the chapter.",
        "Where the student's school format notes conflict with the default template, follow the school format notes unless they require fabrication or academic misconduct.",
        "Use section headings naturally. Do not state that a heading was selected, required by a template, or included to satisfy the app.",
        "Adapt wording to the selected thesis/dissertation/project format, whether standard thesis, applied project, article-based dissertation, qualitative case study, or secondary-data/econometric study.",
    ]

    stream = method_stream.lower()
    if any(term in stream for term in ["secondary", "econometric", "time-series", "time series", "panel"]):
        rules.extend([
            "For secondary-data and econometric studies, do not write as if the study used respondents, questionnaires, interviews, pilot testing, response rate, or survey administration unless the user explicitly supplied primary-data details.",
            "Use dataset, observation, unit of analysis, period, frequency, source, coverage, missing values, transformations, and model specification language rather than respondent-based survey language.",
            "Chapter Three should include data sources, sample period, variable definitions, transformations, model equations, estimator justification, diagnostic tests, robustness checks, software, and reproducibility where those sections are selected.",
            "Chapter Four should use uploaded results or supplied tables to report descriptive statistics, trends, diagnostic tests, econometric model results, robustness checks, and economic or policy interpretation where available.",
            "Avoid unsupported causal interpretation. Use terms such as association, relationship, effect, predictive relationship, or estimated effect according to the design and identification strategy supplied.",
            "Where econometric details are missing, use placeholders such as [insert model specification], [insert data source and period], [insert diagnostic test result], or [insert robustness check] rather than inventing output.",
        ])
    if "time" in stream:
        rules.extend([
            "For time-series studies, address frequency, sample period, stationarity, structural breaks, lag selection, cointegration, serial correlation, model stability, forecasting accuracy, and interpretation of dynamic relationships where relevant and supplied.",
            "Use time-series terminology carefully, for example unit-root test, ARDL, VAR, VECM, ARIMA, GARCH, impulse response, variance decomposition, or error-correction only when the method is supplied or clearly appropriate."
        ])
    if "panel" in stream:
        rules.extend([
            "For panel-data studies, address country/firm/unit coverage, time period, fixed effects, random effects, Hausman test, cross-sectional dependence, heteroskedasticity, serial correlation, endogeneity, robust or clustered standard errors, and dynamic panel methods where relevant and supplied."
        ])
    if "qualitative" in stream:
        rules.extend([
            "For qualitative studies, use participants, documents, cases, interviews, observations, coding, themes, trustworthiness, credibility, transferability, dependability, confirmability, and reflexivity where relevant.",
            "Do not force quantitative statistics, hypotheses, or econometric diagnostics into qualitative chapters unless required by a mixed-methods design."
        ])

    return {
        "selected_format": thesis_format,
        "method_stream": method_stream,
        "format_notes": format_notes,
        "rules": rules,
    }


def _uploaded_results_for_chapter(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    uploaded = profile.get("uploaded_results") or {}
    result = uploaded.get(str(chapter_number))
    if chapter_number == 4 and not result:
        result = uploaded.get("4")
    return result or {}


def _uploaded_chapter_for_revision(profile: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    uploaded = profile.get("uploaded_chapter_sources") or {}
    return uploaded.get(str(chapter_number)) or {}

def _human_scholarly_style_requirements() -> list[str]:
    """Return high-standard academic writing rules for natural, polished chapter drafting."""
    return [
        "Use the selected academic level only as internal depth guidance. Do not mention the selected level, do not say the writing is produced to meet a level, and do not include meta-commentary about the project being written at a particular standard.",
        "Write in a mature, natural scholarly voice that resembles a carefully supervised student draft: precise, analytical, context-specific, and free from generic AI patterns.",
        "Avoid very short, clipped sentences except where a short sentence is needed for emphasis, transition, or clarity. Prefer well-developed academic sentences that connect evidence, reasoning, and implication.",
        "Vary sentence structure, but avoid overusing sentence frames such as 'This study...', 'The study...', 'The research problem is...', or 'This section...'.",
        "Do not begin a problem statement with wording such as 'The research problem is that...'. Frame the problem analytically, for example through a tension, contradiction, persistent gap, policy concern, empirical inconsistency, or unresolved practical challenge.",
        "Avoid mechanical, generic, and repetitive AI-style phrasing such as 'in today's world', 'it is important to note', 'this study is very important', 'delve into', 'plays a crucial role', 'it is imperative', and repeated formulaic paragraph openings.",
        "Do not merely list ideas. Build an argument by explaining relationships among concepts, comparing studies, identifying tensions, and showing why the present study is necessary.",
        "Every substantive paragraph should develop one clear idea through a topic sentence, evidence or reasoning, interpretation, and a closing implication linked to the study problem, objective, method, finding, or recommendation.",
        "Use critical synthesis rather than annotated-summary writing, especially in the literature review and discussion chapters.",
        "Integrate theory, empirical evidence, context, methodology, and findings in a way that sounds like a carefully supervised academic draft, not a template.",
        "Maintain discipline-appropriate terminology, but avoid unnecessary verbosity, inflated claims, and promotional language.",
        "Use signposting only where it helps the reader. Do not overuse headings or repeated introductory sentences.",
        "Write in third-person academic style unless the student's institution requires otherwise.",
        "Keep the work defensible: do not overstate contribution, causality, generalisability, or policy implications beyond the evidence supplied.",
    ]


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
        ]

    if chapter_number == 3:
        return common + [
            "Write Chapter Three as a completed final project, dissertation, or thesis chapter, not as a proposal.",
            "Use past tense and completed-study wording throughout Chapter Three, for example: 'the study adopted', 'data were collected', 'respondents were selected', 'the questionnaire was administered', and 'the data were analysed'.",
            "Do not use proposal-style future tense such as 'will adopt', 'will collect', 'will be used', 'will be analysed', 'will be administered', 'will be obtained', or 'will be conducted'.",
            "If a detail has not been supplied, use a past-tense placeholder, for example '[insert sampling procedure used]' or '[insert data collection period]', not future-tense wording.",
            "Maintain consistency among philosophy, approach, design, sampling, instrument, validity, reliability, analysis, and ethics.",
        ]

    if chapter_number == 4:
        return common + [
            "Present results objective by objective.",
            "Use uploaded results, statistical output, qualitative coding output, or analysis tables where available.",
            "Convert uploaded software output into clear academic tables and narrative interpretation where possible.",
            "Map each result to the relevant research objective or hypothesis.",
            "Use placeholders for statistical output only where actual results have not been supplied.",
            "Do not invent coefficients, p-values, sample sizes, reliability values, model fit statistics, themes, or quotations.",
            "Where the uploaded output is unclear or incomplete, state what additional output is needed instead of making unsupported claims.",
        ]

    if chapter_number == 5:
        return common + [
            "Base summaries, conclusions, recommendations, and future research suggestions only on supplied findings.",
            "Ensure each recommendation can be traced to a finding.",
        ]

    return common


def build_drafting_prompt(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    revision_mode: bool = False,
    revision_instructions: str = "",
) -> str:
    chapter = get_chapter(chapter_number)
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
            "chapter_title": chapter.get("chapter_title"),
        },
        "project_profile": profile,
        "selected_academic_level_and_depth": _level_depth_requirements(profile),
        "format_and_method_requirements": _format_and_method_requirements(profile),
        "reference_currency_requirements": _reference_currency_requirements(),
        "citation_and_evidence_requirements": _citation_and_evidence_requirements(chapter_number),
        "human_scholarly_style_requirements": _human_scholarly_style_requirements(),
        "uploaded_results_for_this_chapter": _uploaded_results_for_chapter(profile, chapter_number),
        "revision_request": {
            "revision_mode": revision_mode,
            "revision_instructions": revision_instructions,
            "uploaded_chapter_source": _uploaded_chapter_for_revision(profile, chapter_number),
            "revision_output_rules": [
                "When revision_mode is true, revise the uploaded chapter rather than drafting from scratch.",
                "Preserve accurate content from the uploaded chapter where it remains relevant and defensible.",
                "Apply the student's revision instructions, selected sections, school format, scholarly style rules, citation rules, and compliance requirements.",
                "Mark all new or substantially inserted wording exactly as {{ADD: inserted text}} so the interface and DOCX export can show it in red.",
                "Mark proposed removals only when necessary as {{DEL: text to remove}}. Do not overuse deletion markers.",
                "Do not use native Word tracked-change XML. Use the change markers exactly as specified for red inserted text and tracked-style export.",
                "Do not include an editor's memo unless the student explicitly asks for one. Return the revised chapter text only."
            ],
        },
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "chapter_specific_requirements": _chapter_specific_requirements(chapter_number),
        "output_requirements": [
            "Write in formal British English.",
            "Use the selected academic level internally to determine depth and sophistication, but never mention the selected level in the generated chapter text.",
            "Follow the human_scholarly_style_requirements so the writing sounds natural, rigorous, context-specific, and carefully supervised rather than generic or mechanical.",
            "Avoid very short sentences except where they are necessary for emphasis, transition, or clarity.",
            "Do not write sentences that say the work, chapter, section, depth, or argument is designed to meet the selected level of the project, thesis, or dissertation.",
            "Use the reference_currency_requirements: aim for at least 70% of substantive references within the stated recent-reference window, but where current sources do not exist, use the strongest credible available sources instead.",
            "Use the citation_and_evidence_requirements: include relevant, accurate in-text citations across all substantive write-up sections, especially literature, methodology justification, discussion, and problem framing.",
            "For Chapter One, make the Background and Statement of the Problem factual and evidence-led. Use relevant accurate statistics, policy evidence, institutional evidence, or empirical findings to support the problem where supplied or confidently known.",
            "Do not fabricate citations, statistics, or reference-list entries. Use verified/supplied citations and facts where available. Where a required source, statistic, or fact is not supplied or cannot be stated confidently, insert a bracketed placeholder rather than inventing it.",
            "Use clear numbered headings matching the selected sections.",
            "Draft only the selected sections and treat them as the student's school-specific format. Do not force a single institutional structure where the user has selected different sections.",
            "Apply the format_and_method_requirements so the chapter fits the selected thesis format and data orientation.",
            "For secondary data and econometric studies, avoid survey-only language unless primary data details were supplied. Use dataset, observation, model, period, frequency, estimator, diagnostic, and robustness language where relevant.",
            "Use analytical and connective prose: show why each point matters to the study rather than merely naming concepts, authors, variables, or methods.",
            "Avoid weak or unscholarly problem-statement phrasing such as 'The research problem is that...'. Use an evidence-led academic formulation instead.",
            "Write as a completed academic project, dissertation, or thesis. Avoid proposal-style future tense across the write-up, except where Chapter Five legitimately suggests future research using 'should', 'could', or 'may'.",
            "Prefer precise, discipline-appropriate wording over exaggerated claims or promotional language.",
            "Do not invent fabricated references, statistics, ethical approvals, sample sizes, or data results.",
            "Where evidence is missing, write a bracketed placeholder such as [insert recent empirical evidence].",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "Use markdown tables only where a table is clearly requested or useful.",
            "For Chapter Two tables, use a properly structured markdown table with meaningful column headers and one idea per cell.",
            "For Chapter Three, use past tense for completed project work and avoid future-tense proposal wording.",
            "For Chapter Four, first use any uploaded results or analysis output attached to the project profile, then use the student answers. Use placeholders only where actual output has not been supplied.",
            "For Chapter Four, report only results found in uploaded files or student answers. Do not fabricate numbers, tables, themes, or interpretation.",
            "For Chapter Five, base conclusions and recommendations only on findings supplied in the profile or answers.",
            "When revising an uploaded chapter, edit the uploaded text according to the student's instructions and mark new insertions with {{ADD: ...}} so they appear red in preview and exported DOCX.",
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

def generate_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    use_ai: bool = True,
    revision_mode: bool = False,
    revision_instructions: str = "",
) -> tuple[str, str]:
    prompt = build_drafting_prompt(
        profile,
        chapter_number,
        selected_section_ids,
        answers,
        extra_instructions,
        revision_mode=revision_mode,
        revision_instructions=revision_instructions,
    )
    client = _safe_get_openai_client()
    if use_ai and client:
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        instructions = (
            "You are ProjectReady AI, an academic project-work drafting and compliance assistant. "
            "You help students draft chapters from selected guidelines. You support learning and compliance. "
            "Write in a natural, high-standard scholarly voice that sounds like a carefully supervised academic draft, not generic AI prose. "
            "Use the selected academic level only to determine depth; never mention the selected level or say the chapter is written to meet a level, checklist, template, or software requirement. "
            "Avoid generic AI-style phrasing, repetition, filler, overclaiming, template-like prose, and very short choppy sentences except where a short sentence is needed for clarity. "
            "Build coherent academic arguments with critical synthesis, contextual relevance, and defensible reasoning. "
            "Do not begin the problem statement with phrases such as 'The research problem is that'; frame the problem through evidence, contradiction, gap, policy concern, or unresolved practical challenge. "
            "You do not fabricate sources, results, approvals, page numbers, or evidence. "
            "When the user has not provided facts, use clear placeholders rather than inventing content. "
            "Write as a completed final project, dissertation, or thesis. Avoid proposal-style future tense across chapters, especially Chapter Three methodology. "
            "For Chapter Two, format literature gap tables as clean markdown tables with clear columns. "
            "For Chapter Four, use uploaded results files where available and never invent analysis output. "
            "Let the selected thesis, dissertation, or project-work level guide depth silently without appearing in the chapter text. "
            "Make each section read like publishable or supervisor-ready academic prose, with a clear line of reasoning and strong paragraph development. "
            "Apply the reference currency rule: aim for most substantive citations to be from the last five years, but where recent literature does not exist, use credible available sources, including foundational theories and essential older studies. "
            "Include relevant and accurate in-text citations throughout the write-up. For the problem statement, use factual evidence and accurate statistics to show that the problem exists, where those facts are supplied or can be stated confidently. "
            "Do not fabricate citations, references, statistics, or institutional evidence. Use clear bracketed placeholders only when a credible source, fact, or statistic is not available or has not been supplied. "
            "Support many institutional thesis formats by treating the selected sections and school-specific notes as the governing structure. "
            "For secondary data and econometric work, use appropriate dataset, model, estimator, diagnostic, robustness, and economic interpretation language instead of primary survey wording unless primary data were actually used. "
            "When revision mode is enabled, revise the uploaded chapter as the base text. Preserve sound content, apply the supplied instruction, and mark all new insertions exactly as {{ADD: inserted text}}. Mark proposed removals only when necessary as {{DEL: text}}."
        )
        response = client.responses.create(model=model, instructions=instructions, input=prompt)
        text = getattr(response, "output_text", "").strip()
        if text:
            return _polish_generated_text(text), "openai_responses_api"

    return _polish_generated_text(generate_fallback_chapter(
        profile,
        chapter_number,
        selected_section_ids,
        answers,
        revision_mode=revision_mode,
        revision_instructions=revision_instructions,
    )), "local_template_fallback"


def generate_fallback_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    revision_mode: bool = False,
    revision_instructions: str = "",
) -> str:
    chapter = get_chapter(chapter_number)
    sections = selected_sections(chapter_number, selected_section_ids)
    answers = answers or {}

    title = profile.get("title", "[Project Title]")
    level_info = _level_depth_requirements(profile)
    ref_info = _reference_currency_requirements()
    lines = [
        f"# CHAPTER {chapter_number}",
        f"# {chapter.get('chapter_title', '').upper()}",
        "",
        f"Study title: {title}",
        "",
    ]

    if revision_mode:
        uploaded_source = _uploaded_chapter_for_revision(profile, chapter_number)
        source_preview = str(uploaded_source.get("preview") or uploaded_source.get("text") or "").strip()
        lines.extend([
            "## Revision Source Note",
            "",
            f"The revised version should be developed from the uploaded chapter file **{uploaded_source.get('filename', 'uploaded chapter')}** and the supplied revision instruction.",
            f"Revision instruction: {revision_instructions or '[insert revision instruction]'}",
            "New insertions should be marked as {{ADD: red inserted text}} and proposed removals as {{DEL: text to remove}}.",
            "",
        ])
        if source_preview:
            lines.extend([
                "## Uploaded Chapter Extract",
                "",
                source_preview[:2500],
                "",
                "{{ADD: [insert revised and improved text based on the uploaded chapter and the student's instruction]}}",
                "",
            ])

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
        stream = str(profile.get("method_stream") or profile.get("data_type") or "").lower()
        if any(term in stream for term in ["secondary", "econometric", "time-series", "time series", "panel"]):
            return (
                f"This section requires the secondary-data and econometric details that were actually used in {title}. "
                f"The account should remain in past tense and should cover these expectations: {requirements} "
                f"[insert data source, period, unit of analysis, variable construction, model specification, estimator, diagnostics, robustness checks, software, and verified methodological citations here]."
            )
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

    lines: list[str] = []
    if uploaded:
        lines.append(
            f"The results write-up should be developed from the uploaded file **{uploaded.get('filename', 'results file')}**. "
            f"The extracted output contains {uploaded.get('characters_extracted', 0)} characters. "
            "Only statistics, themes, tables, and findings that appear in the uploaded output should be reported."
        )
        preview = str(uploaded.get("preview") or "").strip()
        if preview:
            lines.append("\n**Extracted results preview:**\n")
            lines.append(preview[:1800])
    else:
        lines.append(
            "No result file has been uploaded for this chapter. Upload SPSS, Excel, CSV, Word, PDF, or text output, or paste the key results in the guided questions. "
            "Until results are supplied, the chapter should use placeholders rather than invented statistics."
        )

    if objectives:
        lines.append("\n**Objective-to-results mapping template:**\n")
        lines.append("| Research Objective | Uploaded Result/Table | Interpretation Required | Discussion Link |")
        lines.append("|---|---|---|---|")
        for objective in objectives:
            lines.append(f"| {objective} | [identify table/statistic/theme from uploaded output] | [interpret the result] | [link to theory and prior studies] |")

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
