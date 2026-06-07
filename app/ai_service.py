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

def _chapter_specific_requirements(chapter_number: int) -> list[str]:
    """Return chapter-level drafting rules that apply beyond section rules."""
    common = [
        "Use valid markdown for headings, paragraphs, lists, and tables.",
        "Keep paragraphs coherent and academic, with clear topic sentences and transitions.",
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
        "reference_currency_requirements": _reference_currency_requirements(),
        "uploaded_results_for_this_chapter": _uploaded_results_for_chapter(profile, chapter_number),
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "chapter_specific_requirements": _chapter_specific_requirements(chapter_number),
        "output_requirements": [
            "Write in formal British English.",
            "Write at the academic depth expected of the selected level in selected_academic_level_and_depth.",
            "Use the reference_currency_requirements: aim for at least 70% of substantive references within the stated recent-reference window, but where current sources do not exist, use the strongest credible available sources instead.",
            "Do not fabricate citations or reference-list entries. Use verified/supplied citations where available. Where a required source is not supplied or cannot be stated confidently, insert a bracketed reference placeholder rather than inventing a source.",
            "Use clear numbered headings matching the selected sections.",
            "Draft only the selected sections.",
            "Do not invent fabricated references, statistics, ethical approvals, sample sizes, or data results.",
            "Where evidence is missing, write a bracketed placeholder such as [insert recent empirical evidence].",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "Use markdown tables only where a table is clearly requested or useful.",
            "For Chapter Two tables, use a properly structured markdown table with meaningful column headers and one idea per cell.",
            "For Chapter Three, use past tense for completed project work and avoid future-tense proposal wording.",
            "For Chapter Four, first use any uploaded results or analysis output attached to the project profile, then use the student answers. Use placeholders only where actual output has not been supplied.",
            "For Chapter Four, report only results found in uploaded files or student answers. Do not fabricate numbers, tables, themes, or interpretation.",
            "For Chapter Five, base conclusions and recommendations only on findings supplied in the profile or answers.",
        ],
    }
    return json.dumps(prompt, ensure_ascii=False, indent=2)


def generate_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
    extra_instructions: str = "",
    use_ai: bool = True,
) -> tuple[str, str]:
    prompt = build_drafting_prompt(profile, chapter_number, selected_section_ids, answers, extra_instructions)
    client = _safe_get_openai_client()
    if use_ai and client:
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        instructions = (
            "You are ProjectReady AI, an academic project-work drafting and compliance assistant. "
            "You help students draft chapters from selected guidelines. You support learning and compliance. "
            "You do not fabricate sources, results, approvals, page numbers, or evidence. "
            "When the user has not provided facts, use clear placeholders rather than inventing content. "
            "For Chapter Three methodology in final project mode, write in past tense and avoid proposal-style future tense. "
            "For Chapter Two, format literature gap tables as clean markdown tables with clear columns. "
            "For Chapter Four, use uploaded results files where available and never invent analysis output. "
            "Always write at the selected thesis, dissertation, or project-work level. "
            "Apply the reference currency rule: aim for most substantive citations to be from the last five years, but where recent literature does not exist, use credible available sources, including foundational theories and essential older studies. "
            "Do not fabricate citations or references. Use placeholders only when a credible source is not available or has not been supplied."
        )
        response = client.responses.create(model=model, instructions=instructions, input=prompt)
        text = getattr(response, "output_text", "").strip()
        if text:
            return text, "openai_responses_api"

    return generate_fallback_chapter(profile, chapter_number, selected_section_ids, answers), "local_template_fallback"


def generate_fallback_chapter(
    profile: dict[str, Any],
    chapter_number: int,
    selected_section_ids: list[str],
    answers: dict[str, Any] | None = None,
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
        f"Academic level: {level_info['selected_level']}",
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
            f"This section was developed using the information supplied by the student. "
            f"Key information provided: {answer_text}. The section addressed the following methodological expectations: {rules_text}. "
            f"It should be refined with supervisor-approved details, exact dates, instruments, approvals, and citations before final submission."
        )

    return (
        f"This section should be developed using the information supplied by the student. "
        f"Key information provided: {answer_text}. The writing should satisfy the following guideline expectations: {rules_text}. "
        f"The section should be refined with recent evidence, relevant citations, and supervisor-approved details before final submission."
    )


def _placeholder_paragraph(section_title: str, rules: list[str], profile: dict[str, Any], chapter_number: int) -> str:
    title = profile.get("title", "the study")
    requirements = " ".join(rules[:4]) if rules else "Follow the selected institutional requirements."

    if chapter_number == 3:
        return (
            f"This section was drafted for {title}. The student must insert the project-specific methodological details that were used in the study. "
            f"Guideline focus: {requirements} [insert study-specific methods, approvals, evidence, and citations here]."
        )

    return (
        f"This section will be drafted for {title}. The student must provide the required project-specific information. "
        f"Guideline focus: {requirements} [provide study-specific details, evidence, and citations here]."
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
