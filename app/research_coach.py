from __future__ import annotations

import os
from typing import Any

from app.ai_service import _call_openai_response_safely, _safe_get_openai_client
from app.research_journey import approach_family, research_record


def _context_text(project: dict[str, Any]) -> str:
    profile = project.get("profile") or {}
    record = research_record(profile, str(project.get("title") or ""))
    logic = record["logic"]
    method = record["method"]
    return "\n".join([
        f"Research title: {record['identity']['title'] or '[not confirmed]'}",
        f"Academic level: {record['identity']['level'] or '[not confirmed]'}",
        f"Research area: {record['identity']['research_area'] or '[not confirmed]'}",
        f"Study context: {record['identity']['study_context'] or '[not confirmed]'}",
        f"Approach family: {approach_family(profile)}",
        "Objectives: " + (" | ".join(logic["objectives"]) or "[not confirmed]"),
        "Research questions: " + (" | ".join(logic["research_questions"]) or "[not confirmed]"),
        "Hypotheses: " + (" | ".join(logic["hypotheses"]) or "[not confirmed/not applicable]"),
        "Variables/constructs: " + (" | ".join(logic["variables"]) or "[not confirmed]"),
        f"Theoretical framework: {record['theory_framework']['theoretical_framework'] or '[not confirmed]'}",
        f"Research design: {method['research_design'] or '[not confirmed]'}",
        f"Sampling strategy: {method['sampling_strategy'] or '[not confirmed]'}",
        f"Analysis plan: {method['analysis_plan'] or '[not confirmed]'}",
    ])


def _fallback(project: dict[str, Any], mode: str, question: str) -> dict[str, Any]:
    profile = project.get("profile") or {}
    family = approach_family(profile)
    mode = (mode or "explain").strip().lower()
    title = str(project.get("title") or profile.get("title") or "your study")
    if mode == "guide":
        response = (
            f"For {title}, work through this decision in sequence rather than choosing automatically.\n\n"
            "1. Restate the exact research objective or question the decision must serve.\n"
            "2. Identify what evidence or information you already have.\n"
            "3. Identify the missing information that would change the decision.\n"
            "4. Compare the defensible alternatives and their limitations.\n"
            "5. Select the option that matches the approved study and record your rationale in My Research Record.\n\n"
            f"Your question was: {question}\n\n"
            "ProjectReady should recommend and explain, but the researcher should confirm the final research decision."
        )
    elif mode in {"decide", "help_me_decide", "decision"}:
        response = (
            f"Use a comparison decision for {title}. The current project is treated as {family.replace('_', ' ')}. "
            "Compare each option against: fit with the objective/question, data required, assumptions, feasibility, interpretive limits, and what you could defend to a supervisor or examiner. "
            f"Do not choose solely because an option is more sophisticated. Your decision question is: {question}\n\n"
            "After comparing the options, record the selected approach and a short rationale in the Research Decision checkpoint."
        )
    elif mode == "viva":
        response = (
            f"Use the question '{question}' as a viva rehearsal for {title}. Structure the answer in five parts: "
            "what you decided, why it fits the study, what evidence or theory supports the decision, what limitation remains, and what alternative you considered. "
            "Avoid claiming causation, representativeness, statistical significance, policy effects or source findings unless those are established by the actual thesis evidence."
        )
    else:
        response = (
            f"For {title}, the concept should be understood in relation to the approved research logic rather than as a generic definition. "
            f"Your question is: {question}\n\n"
            "A sound explanation should clarify what the concept means, why it matters to the stated objective or research question, what information is needed to apply it, and what common interpretation would be incorrect. "
            "Where the project record is incomplete, confirm the missing decision instead of allowing the system to invent it."
        )
    return {"answer": response, "source": "deterministic_research_coach", "mode": mode, "requires_researcher_decision": mode in {"guide", "decide", "help_me_decide", "decision"}}


def coach(project: dict[str, Any], mode: str, question: str) -> dict[str, Any]:
    fallback = _fallback(project, mode, question)
    client = _safe_get_openai_client()
    if not client:
        return fallback
    model = str(os.getenv("OPENAI_COACH_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.6").strip()
    instructions = (
        "You are the ProjectReady Research Coach. Teach and guide the researcher; do not ghostwrite a thesis section. "
        "Ground every recommendation in the supplied project record. Do not invent facts, citations, statistics, results, ethical approvals, sample details, theories, instruments or institutional rules. "
        "If a necessary research decision is absent, identify it explicitly. Explain alternatives and trade-offs. "
        "For 'guide' mode, ask a short sequence of practical questions. For 'decide' mode, compare defensible alternatives and leave the final decision to the researcher. "
        "For 'viva' mode, give a defence structure and likely follow-up questions based only on the project record. "
        "Keep the response educational and concise enough to use during supervision."
    )
    prompt = f"MODE: {mode}\n\nPROJECT RECORD:\n{_context_text(project)}\n\nRESEARCHER QUESTION:\n{question}"
    answer = _call_openai_response_safely(client, model, instructions, prompt, max_output_tokens=2200)
    if not answer:
        return fallback
    return {"answer": answer, "source": f"openai_research_coach:{model}", "mode": mode, "requires_researcher_decision": str(mode).lower() in {"guide", "decide", "help_me_decide", "decision"}}
