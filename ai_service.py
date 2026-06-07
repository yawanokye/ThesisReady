from __future__ import annotations

import json
import os
import re
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
        "selected_sections": section_payload,
        "extra_instructions": extra_instructions,
        "output_requirements": [
            "Write in formal British English.",
            "Use clear numbered headings matching the selected sections.",
            "Draft only the selected sections.",
            "Do not invent fabricated references, statistics, ethical approvals, sample sizes, or data results.",
            "Where evidence is missing, write a bracketed placeholder such as [insert recent empirical evidence].",
            "Keep variables, objectives, questions, hypotheses, theories, context, and methods internally consistent.",
            "For Chapter Four, use placeholders where actual statistical output has not been supplied.",
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
            "When the user has not provided facts, use clear placeholders rather than inventing content."
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
    lines = [f"# CHAPTER {chapter_number}", f"# {chapter.get('chapter_title', '').upper()}", "", f"Study title: {title}", ""]

    for index, section in enumerate(sections, 1):
        section_title = section["section_title"]
        section_answers = answers.get(section["section_id"], {})
        lines.append(f"## {chapter_number}.{index} {section_title}")
        lines.append("")
        if section_answers:
            lines.append(_draft_from_answers(section_title, section.get("rules", []), section_answers, profile))
        else:
            lines.append(_placeholder_paragraph(section_title, section.get("rules", []), profile))
        lines.append("")
    return "\n".join(lines).strip()


def _draft_from_answers(section_title: str, rules: list[str], section_answers: dict[str, Any], profile: dict[str, Any]) -> str:
    joined_answers = []
    for key, value in section_answers.items():
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if str(v).strip())
        if str(value).strip():
            joined_answers.append(f"{key}: {value}")
    answer_text = " ".join(joined_answers)
    if not answer_text:
        return _placeholder_paragraph(section_title, rules, profile)

    rules_text = " ".join(rules[:3])
    return (
        f"This section should be developed using the information supplied by the student. "
        f"Key information provided: {answer_text}. The writing should satisfy the following guideline expectations: {rules_text}. "
        f"The section should be refined with recent evidence, relevant citations, and supervisor-approved details before final submission."
    )


def _placeholder_paragraph(section_title: str, rules: list[str], profile: dict[str, Any]) -> str:
    title = profile.get("title", "the study")
    requirements = " ".join(rules[:4]) if rules else "Follow the selected institutional requirements."
    return (
        f"This section will be drafted for {title}. The student must provide the required project-specific information. "
        f"Guideline focus: {requirements} [provide study-specific details, evidence, and citations here]."
    )


def split_paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return blocks
