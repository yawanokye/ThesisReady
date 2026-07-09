from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime
from typing import Any

try:
    from app.source_finder import search_literature_sources
except Exception:  # pragma: no cover
    search_literature_sources = None

# Dynamic source context defaults are controlled through helpers below.  Keep this
# reasonably high because journal articles need deeper citation coverage than a
# thesis chapter subsection.
MAX_SOURCE_CONTEXT = int(os.getenv("PROJECTREADY_ARTICLE_MAX_SOURCE_CONTEXT", "80"))

_RETRACTION_TERMS = re.compile(
    r"\b(retracted|retraction\s+notice|withdrawn|removed\s+article|expression\s+of\s+concern|erratum\s+to\s+retracted)\b",
    flags=re.IGNORECASE,
)

_ATTENTION_RE = re.compile(
    r"\[(?:insert|verify|confirm|provide|supply|complete|replace|check|add|update|obtain|state|specify|include)\b[^\]]*\]",
    flags=re.IGNORECASE,
)

_ADAM_2020_REFERENCE = (
    "Adam, A. M. (2020). Sample size determination in survey research. "
    "Journal of Scientific Research and Reports, 26(5), 90-97. "
    "https://journaljsrr.com/index.php/JSRR/article/view/1154"
)


def _safe_get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _select_article_model(level: str, article_type: str = "") -> str:
    """Route journal article drafting by academic depth and publication complexity."""
    level_l = (level or "").strip().lower()
    type_l = (article_type or "").strip().lower()
    is_doctoral = any(token in level_l for token in ["phd", "doctor", "dba", "ded", "professional doctorate"])
    is_research_masters = "research masters" in level_l or "mphil" in level_l
    is_review_article = any(token in type_l for token in ["systematic", "scoping", "meta-analysis", "meta analysis", "review article", "literature review", "conceptual"])
    if is_doctoral:
        return os.getenv("OPENAI_ARTICLE_DOCTORAL_MODEL", os.getenv("OPENAI_DOCTORAL_DRAFT_MODEL", "gpt-5.5")).strip()
    if is_research_masters or is_review_article:
        return os.getenv("OPENAI_ARTICLE_RESEARCH_MODEL", os.getenv("OPENAI_RESEARCH_MASTERS_DRAFT_MODEL", "gpt-5.5")).strip()
    if "non-research" in level_l or "master" in level_l:
        return os.getenv("OPENAI_ARTICLE_MASTERS_MODEL", "gpt-5.4").strip()
    return os.getenv("OPENAI_ARTICLE_BACHELOR_MODEL", os.getenv("OPENAI_BACHELOR_DRAFT_MODEL", "gpt-5.4")).strip()


def _article_kind(article_type: str) -> str:
    t = (article_type or "").lower()
    if any(x in t for x in ["systematic", "meta-analysis", "meta analysis"]):
        return "systematic_review_or_meta_analysis"
    if any(x in t for x in ["review", "literature review", "scoping"]):
        return "review_article_or_literature_review"
    if any(x in t for x in ["short", "brief", "communication"]):
        return "short_communication_or_brief_report"
    if "conference" in t:
        return "conference_paper"
    return "standard_research_article"


def _article_reference_expectations(article_type: str) -> dict[str, Any]:
    """Return article-type citation-depth guidance without encouraging reference padding."""
    kind = _article_kind(article_type)
    matrix: dict[str, dict[str, Any]] = {
        "standard_research_article": {
            "target_range": "40-60 references",
            "default_search_limit": 60,
            "guidance": "Original research should support the background, theory, methods, results interpretation and discussion with substantial but selective coverage.",
        },
        "review_article_or_literature_review": {
            "target_range": "60-150+ references",
            "default_search_limit": 140,
            "guidance": "Review articles require broad coverage of the relevant literature, including competing streams, methodological differences and unresolved debates.",
        },
        "systematic_review_or_meta_analysis": {
            "target_range": "80-300+ references",
            "default_search_limit": 180,
            "guidance": "Systematic reviews and meta-analyses require exhaustive, transparent coverage consistent with the review protocol and eligibility criteria.",
        },
        "short_communication_or_brief_report": {
            "target_range": "10-25 references",
            "default_search_limit": 30,
            "guidance": "Short communications should use a narrow, high-value reference base because of strict word limits.",
        },
        "conference_paper": {
            "target_range": "15-40 references",
            "default_search_limit": 45,
            "guidance": "Conference papers need enough current literature to justify novelty without overcrowding a short manuscript.",
        },
    }
    out = dict(matrix[kind])
    out["article_kind"] = kind
    out["anti_padding_rule"] = (
        "Do not pad the reference list. Cite only sources that directly support a claim, method, theory, measure, comparison or interpretation. "
        "If available verified sources are fewer than the expected range, add an attention placeholder asking for additional verified literature rather than inventing sources."
    )
    return out


def _article_source_limit(payload: dict[str, Any]) -> int:
    env_limit = os.getenv("PROJECTREADY_ARTICLE_SOURCE_LIMIT", "").strip()
    if env_limit.isdigit():
        return max(1, int(env_limit))
    return int(_article_reference_expectations(str(payload.get("article_type") or "")).get("default_search_limit", 60))


def _looks_retracted(src: dict[str, Any]) -> bool:
    fields = [
        src.get("title"), src.get("type"), src.get("subtype"), src.get("status"), src.get("publication_status"),
        src.get("update_type"), src.get("relation_type"), src.get("abstract"), src.get("note"), src.get("warning"),
    ]
    combined = " ".join(str(x or "") for x in fields)
    if _RETRACTION_TERMS.search(combined):
        return True
    flags = ["is_retracted", "retracted", "has_retraction", "is_withdrawn", "withdrawn", "removed", "expression_of_concern"]
    return any(bool(src.get(flag)) for flag in flags)


def _build_search_profile(payload: dict[str, Any]) -> dict[str, Any]:
    objectives = []
    for raw in str(payload.get("objectives") or "").split("\n"):
        item = raw.strip(" -;,")
        if item:
            objectives.append(item)
    return {
        "title": str(payload.get("article_title") or "").strip(),
        "research_area": str(payload.get("research_area") or payload.get("article_title") or "").strip(),
        "study_context": str(payload.get("context") or "").strip(),
        "level": str(payload.get("academic_level") or "Research Masters (e.g. MPhil)").strip(),
        "research_approach": str(payload.get("methodology") or "").strip(),
        "data_type": str(payload.get("article_type") or "").strip(),
        "objectives": objectives[:8],
        "notes": " ".join([
            str(payload.get("target_journal") or ""),
            str(payload.get("variables_constructs") or ""),
            str(payload.get("key_findings") or ""),
            str(payload.get("theory_or_framework") or ""),
        ]).strip(),
    }


def _search_sources(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not payload.get("include_source_search", True) or search_literature_sources is None:
        return [], [], {"provider_errors": [], "query": ""}
    profile = _build_search_profile(payload)
    query = " ".join([
        str(payload.get("article_title") or ""),
        str(payload.get("research_area") or ""),
        str(payload.get("context") or ""),
        str(payload.get("variables_constructs") or ""),
        str(payload.get("theory_or_framework") or ""),
        str(payload.get("key_findings") or ""),
    ]).strip()
    result = search_literature_sources(
        profile=profile,
        query=query,
        max_results=_article_source_limit(payload),
        include_older_foundational=bool(payload.get("include_older_foundational", True)),
    )
    raw_sources = result.get("sources") or []
    blocked = [s for s in raw_sources if _looks_retracted(s)]
    usable = [s for s in raw_sources if not _looks_retracted(s)]
    return usable, blocked, result


def _source_context(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    max_context = max(1, int(os.getenv("PROJECTREADY_ARTICLE_MAX_SOURCE_CONTEXT", str(MAX_SOURCE_CONTEXT))))
    for idx, src in enumerate(sources[:max_context], start=1):
        authors = src.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        records.append({
            "key": f"S{idx}",
            "title": src.get("title", ""),
            "authors": authors,
            "year": src.get("year", ""),
            "source": src.get("source", ""),
            "doi": src.get("doi", ""),
            "url": src.get("url", ""),
            "abstract": str(src.get("abstract") or "")[: int(os.getenv("PROJECTREADY_ARTICLE_ABSTRACT_CHARS", "700"))],
            "database": src.get("database", ""),
            "relevance_tier": src.get("relevance_tier", ""),
            "citation_count": src.get("citation_count", ""),
            "reference_entry_hint": src.get("apa_hint") or src.get("reference_entry_hint") or "",
        })
    return records


def _extract_text(response: Any) -> str:
    return str(getattr(response, "output_text", "") or "").strip()


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()


def _is_survey_research(payload: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(payload.get(k) or "")
        for k in ["article_type", "methodology", "context", "data", "data_results", "variables_constructs", "objectives", "research_area"]
    ).lower()
    return any(token in haystack for token in ["survey", "questionnaire", "likert", "respondent", "pls-sem", "pls sem", "sem", "cross-sectional"])


def _has_sample_size_determination(payload: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(payload.get(k) or "")
        for k in ["methodology", "data", "data_results", "context", "objectives", "key_findings"]
    ).lower()
    return any(token in haystack for token in ["sample size", "yamane", "krejcie", "morgan", "cochran", "adam (2020)", "power analysis", "g*power", "gpower"])


def _survey_method_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    survey = _is_survey_research(payload)
    if not survey:
        return {"is_survey_research": False, "rules": []}
    rules = [
        "For survey research, include how common method variance/common method bias was addressed in the Methods section, using prose rather than a bare checklist.",
        "Discuss procedural remedies where appropriate: anonymity, voluntary participation, careful item wording, separation of predictor and outcome sections, varied scale anchors where defensible, reduced evaluation apprehension, and clear instructions.",
        "Discuss statistical remedies where appropriate: Harman's single-factor test, marker-variable approach, unmeasured latent method factor, full collinearity VIF, or another method justified by the selected analysis technique.",
        "If PLS-SEM or SEM is used, distinguish measurement-model quality from common-method-bias assessment.",
        "Do not report CMV/CMB statistics unless the user supplied them. Insert [insert CMV/CMB test result] where needed.",
    ]
    if not _has_sample_size_determination(payload):
        rules.append(
            "If the user did not state a sample-size determination method, justify the required sample size using Adam (2020) for survey research and include the Adam (2020) reference. Do not fabricate the final sample size; use [confirm population size and required sample size] where the population size or confidence level is missing."
        )
    return {
        "is_survey_research": True,
        "sample_size_source_if_missing": _ADAM_2020_REFERENCE if not _has_sample_size_determination(payload) else "User supplied another sample-size determination approach.",
        "rules": rules,
    }


def _human_article_style_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "style_goal": "publishable, human-supervised academic prose",
        "rules": [
            "Write in formal British English with natural academic rhythm, not template-like AI prose.",
            "Vary sentence and paragraph length according to argument needs, but keep grammar, citations, headings and tables clean.",
            "Build paragraphs around claim, evidence, interpretation and contribution. Avoid paragraphs that merely list authors.",
            "Use precise verbs such as indicates, qualifies, complicates, supports, constrains, extends and contradicts.",
            "Avoid filler phrases such as 'in today's world', 'it is important to note', 'delve into', 'plays a crucial role', and repeated 'moreover' or 'furthermore'.",
            "Use cautious scholarly judgement rather than promotional language. Do not overclaim practical or theoretical contributions.",
            "Maintain the author's voice through reasoned transitions, context-specific qualifiers and close links between the study objectives, methods, results and contribution.",
            "Do not introduce typos, random grammar errors, lower-case sentence starts, broken citations or artificial mistakes.",
        ],
    }


def _prose_objective_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective_style": "prose-first",
        "rules": [
            "Write the article objective, purpose and contribution in prose. Avoid a bare bullet list of objectives unless the target journal explicitly requires it.",
            "In the Introduction, write objectives as a paragraph such as: 'Accordingly, this article examines..., assesses..., and explains...' rather than listing Objective 1, Objective 2 and Objective 3.",
            "Write all major article sections in prose first. Tables may support the argument, but they must not replace the narrative.",
            "If research questions or hypotheses are needed, introduce them through a short prose bridge before listing or tabulating them.",
        ],
    }


def _equation_and_framework_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "equation_rules": [
            "When equations or statistical models are required, place each equation in a display equation block using $$ equation $$. Use clean Word-friendly mathematical notation with Unicode Greek letters and subscripts where possible.",
            "Define every symbol directly below the equation in prose. Do not leave equations unexplained.",
            "Use article-appropriate model notation, for example Yᵢ = β₀ + β₁X₁ᵢ + β₂X₂ᵢ + εᵢ, but adapt variable names to the user's actual study.",
            "Do not invent coefficients, p-values or model results. Use [insert model estimates] where results are missing.",
        ],
        "conceptual_framework_rules": [
            "If a conceptual framework is required, structure it as: framework narrative, variable architecture table, hypothesised path table, figure caption, and optional Mermaid or Graphviz code block.",
            "Classify variables as IV, DV, MED, MOD and CV where applicable. Do not force mediation or moderation if not supplied or theoretically justified.",
            "For moderation, show the moderator pointing to the relationship being moderated, not as a vague ordinary predictor of the dependent variable.",
            "Avoid messy ASCII diagrams. Use a concise Mermaid flowchart or Graphviz DOT/Python Graphviz code block where a diagram is useful.",
            "Do not hard-code sample variables. Use only variables, constructs and relationships supplied by the user or clearly inferable from the current article input.",
        ],
        "graphviz_guide": {
            "node_types": ["IV", "DV", "MED", "MOD", "CV"],
            "preferred_orientation": "LR for simple causal frameworks, TB for layered or process frameworks",
            "style_note": "Use publication-style boxes, clear arrows and short labels. If the diagram cannot be rendered in the app, output a Graphviz-compatible code block for the user to render externally.",
        },
    }


def _article_prompt_quality_pack(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "human_article_style_requirements": _human_article_style_requirements(payload),
        "prose_objective_requirements": _prose_objective_requirements(payload),
        "survey_method_requirements": _survey_method_requirements(payload),
        "equation_and_framework_requirements": _equation_and_framework_requirements(payload),
        "reference_depth_requirements": _article_reference_expectations(str(payload.get("article_type") or "")),
    }


def _light_human_article_polish(text: str) -> str:
    """Safe text polish adapted from ai_service.py, without artificial errors."""
    if not text:
        return text
    replacements = {
        r"\bin today's world\b": "in the present context",
        r"\bit is important to note that\b": "",
        r"\bdelve into\b": "examine",
        r"\bplays a crucial role\b": "is important",
        r"\bvarious factors\b": "specific factors",
        r"\bsignificant impact\b": "meaningful effect",
        r"\bthis highlights the importance of\b": "this indicates why",
        r"\bmoreover,\s+moreover\b": "moreover",
        r"\bfurthermore,\s+furthermore\b": "furthermore",
    }
    out = text
    for pattern, repl in replacements.items():
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def _fallback_article(payload: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    title = str(payload.get("article_title") or "Article Draft").strip()
    article_type = str(payload.get("article_type") or "Empirical research article").strip()
    citation_style = str(payload.get("citation_style") or "APA 7th").strip()
    ref_expectation = _article_reference_expectations(article_type)
    survey_rules = _survey_method_requirements(payload)
    source_note = ""
    if sources:
        source_note = "\n\nThe draft should be strengthened with reviewed source records such as: " + "; ".join(
            f"S{i+1}: {s.get('title', 'Untitled')} ({s.get('year', 'n.d.')})" for i, s in enumerate(sources[:8])
        )
    survey_note = ""
    if survey_rules.get("is_survey_research"):
        survey_note = (
            "\n\nFor survey research, this Methods section should explain sample-size determination, questionnaire development, "
            "validity, reliability and common method variance/common method bias remedies. If no sample-size method has been supplied, use Adam (2020) as the sample-size determination source and verify the final population size and required sample size."
        )
    return f"""# {title}

## Article Type and Target

This manuscript is being prepared as a {article_type}. The target journal is {payload.get('target_journal') or '[insert target journal]'}. The expected reference depth for this article type is {ref_expectation['target_range']}, but the final reference list must include only sources cited in the manuscript.

## Abstract

[insert 180-250 word structured or unstructured abstract after confirming the final results, sample, method and contribution]

## Keywords

[insert 4-6 keywords]

## 1. Introduction

This section should establish the research problem, the current scholarly conversation, the study context and the article's contribution. The article objective should be written in prose rather than as a bare list. {source_note}

## 2. Literature Review and Theoretical Positioning

[insert focused literature synthesis using verified current sources and foundational theory where appropriate]

## 3. Conceptual or Analytical Framework

[insert framework narrative, variable architecture table, hypothesised path table, and Mermaid or Graphviz code block where applicable]

## 4. Methods

[insert article-ready methods section, including design, setting, population/sample, data source, measures, analysis technique, validity/reliability or trustworthiness, and ethics]{survey_note}

## 5. Results

[insert analysed results, tables and figures. Do not invent statistics, coefficients, themes or p-values]

## 6. Discussion

[insert interpretation of findings against theory, prior studies and the study context]

## 7. Conclusion

[insert concise conclusion, contribution, limitations and future research]

## Declarations

Funding: [confirm funding statement]

Conflict of interest: [confirm conflict-of-interest statement]

Ethics approval: [confirm ethics approval or exemption]

Data availability: [confirm data availability statement]

## References

[insert {citation_style} references for sources cited in the article only]
""".strip()


def _finalise_article_text(text: str) -> str:
    text = _strip_code_fences(text or "")
    text = re.sub(r"<span\s+[^>]*>(.*?)</span>", r"\1", text, flags=re.I | re.S)
    text = text.replace("—", ", ").replace(" – ", ", ").replace("–", "-").replace("‑", "-")
    text = _light_human_article_polish(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def draft_journal_article(payload: dict[str, Any]) -> dict[str, Any]:
    if not str(payload.get("article_title") or "").strip():
        raise ValueError("Article title or working topic is required.")
    sources, blocked, search_result = _search_sources(payload)
    source_records = _source_context(sources)
    model = _select_article_model(str(payload.get("academic_level") or ""), str(payload.get("article_type") or ""))
    client = _safe_get_openai_client()
    provider_errors = search_result.get("provider_errors") or [] if isinstance(search_result, dict) else []

    if not client or os.getenv("PROJECTREADY_ARTICLE_USE_AI", "1").strip().lower() in {"0", "false", "no"}:
        article_text = _fallback_article(payload, sources)
        mode = "metadata_fallback"
    else:
        current_year = datetime.now().year
        quality_pack = _article_prompt_quality_pack(payload)
        prompt = {
            "task": "Draft a publishable journal article manuscript from the user's inputs and current scholarly metadata.",
            "article_inputs": payload,
            "current_year": current_year,
            "source_records": source_records,
            "quality_pack": quality_pack,
            "strict_rules": [
                "Use the target journal guidelines supplied by the user as formatting and structural rules. If they are missing, use a standard scholarly article structure appropriate to the article type.",
                "Do not guarantee publication. Produce a journal-article-ready draft that still requires author verification, supervisor review and journal formatting checks.",
                "Do not fabricate results, sample sizes, p-values, coefficients, themes, quotations, ethics approvals, funding, conflicts of interest, datasets or citations.",
                "Use bracketed attention placeholders where details are missing, for example [confirm sample size], [insert regression table], [verify ethics approval] or [insert target journal word limit].",
                "Use only supplied source records, user-provided reference notes or sources that can be stated with confidence. Do not invent references.",
                "Never use retracted, withdrawn, removed or expression-of-concern sources to support any argument, table, citation or reference entry.",
                "Keep citations accurate and include a References section containing only cited sources.",
                "Respect the selected citation style and target journal notes where possible.",
                "Write in polished formal British English with clear, publishable argument, natural academic rhythm and context-specific judgement.",
                "Minimise em dashes and en dashes; use commas, semicolons, colons, parentheses or separate sentences instead.",
                "Write the objective, purpose and contribution in prose, not as a bare objective list, unless the target journal explicitly requires objective bullets.",
                "As much as possible, write all manuscript sections in prose. Use tables only to clarify dense information, not to replace the article narrative.",
                "Increase citation depth according to the article reference-depth rules. Do not pad references; add [insert additional verified literature] if the available source bank is too thin.",
                "For survey research, include common method variance/common method bias procedures and results placeholders where necessary.",
                "If survey sample-size determination is missing, use Adam (2020) as the sample-size determination source and include the Adam (2020) reference if cited.",
                "Use display equation blocks with $$ for equations and define all symbols below the equation.",
                "For conceptual frameworks, include a prose framework narrative, variable architecture table, hypothesised path table and a Mermaid or Graphviz code block where useful.",
            ],
            "recommended_article_structures": {
                "empirical": ["Title", "Abstract", "Keywords", "Introduction", "Literature Review/Theory", "Conceptual or Analytical Framework", "Methods", "Results", "Discussion", "Conclusion", "Declarations", "References"],
                "systematic_review": ["Title", "Abstract", "Keywords", "Introduction", "Methods", "Results", "Discussion", "Conclusion", "References"],
                "conceptual": ["Title", "Abstract", "Keywords", "Introduction", "Conceptual/Theoretical Background", "Proposed Framework", "Discussion", "Implications", "Conclusion", "References"],
                "case_study": ["Title", "Abstract", "Keywords", "Introduction", "Case Context", "Methods", "Findings", "Discussion", "Conclusion", "References"],
            },
            "mandatory_reference_if_used": {
                "Adam_2020_sample_size": _ADAM_2020_REFERENCE,
                "when_to_use": "Use only when the article is survey-based and the user has not supplied another sample-size determination method.",
            },
            "output_format": [
                "Return Markdown only.",
                "Use clean numbered headings where appropriate.",
                "Use prose before tables in each major section.",
                "Use compact tables only when they improve clarity.",
                "Use $$ display equation blocks for equations.",
                "Use Mermaid or Graphviz code blocks for conceptual framework diagrams where useful.",
                "Include an Article Readiness Checklist at the end with missing items and actions.",
            ],
        }
        try:
            response = client.responses.create(
                model=model,
                instructions=(
                    "You are ProjectReady AI's journal article drafting assistant. Draft publishable-quality academic manuscripts from verified inputs. "
                    "Follow journal guidelines when supplied. Use current, non-retracted source metadata for literature framing. "
                    "Write in a human-supervised scholarly voice with prose-led objectives, strong citation depth, methodological care, clean equations and structured conceptual frameworks. "
                    "Do not invent evidence, citations, results or declarations. Use bracketed attention placeholders for missing information."
                ),
                input=json.dumps(prompt, ensure_ascii=False, indent=2),
            )
            article_text = _extract_text(response) or _fallback_article(payload, sources)
            mode = "ai_draft"
        except Exception as exc:
            provider_errors = provider_errors + [f"OpenAI article drafting failed: {str(exc)[:180]}"]
            article_text = _fallback_article(payload, sources)
            mode = "metadata_fallback_after_ai_error"

    article_text = _finalise_article_text(article_text)
    return {
        "article_text": article_text,
        "model_used": model if client else "none",
        "mode": mode,
        "source_records_used": source_records,
        "excluded_retracted_count": len(blocked),
        "excluded_retracted_titles": [str(s.get("title") or "Untitled") for s in blocked[:10]],
        "provider_errors": provider_errors,
        "reference_depth_guidance": _article_reference_expectations(str(payload.get("article_type") or "")),
        "quality_filters": [
            "Retracted, withdrawn, removed and expression-of-concern records excluded where detectable in metadata.",
            "References limited to cited and verified/supplied sources.",
            "Missing article details rendered as bracketed attention placeholders.",
            "Survey articles require CMV/CMB handling in the Methods section.",
            "Adam (2020) is used for survey sample-size determination only when no other sample-size method is supplied.",
            "Equations are requested as display equation blocks and conceptual frameworks as structured framework outputs.",
        ],
    }


def _add_inline_runs(paragraph, text: str) -> None:
    """Add basic bold/italic and attention placeholder styling to a paragraph."""
    from docx.shared import RGBColor
    pos = 0
    token_re = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\])")
    for match in token_re.finditer(text):
        if match.start() > pos:
            paragraph.add_run(text[pos:match.start()])
        token = match.group(0)
        run_text = token
        bold = False
        italic = False
        if token.startswith("**") and token.endswith("**"):
            run_text = token[2:-2]
            bold = True
        elif token.startswith("*") and token.endswith("*"):
            run_text = token[1:-1]
            italic = True
        run = paragraph.add_run(run_text)
        run.bold = bold
        run.italic = italic
        if _ATTENTION_RE.fullmatch(token):
            run.font.color.rgb = RGBColor(192, 0, 0)
        pos = match.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _add_markdown_table(doc, lines: list[str]) -> None:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and not all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
            rows.append(cells)
    if not rows:
        return
    width = max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=width)
    table.style = "Table Grid"
    for row_idx, cells in enumerate(rows):
        row = table.add_row().cells
        for i in range(width):
            row[i].text = cells[i] if i < len(cells) else ""
        if row_idx == 0:
            for cell in row:
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True


def _add_equation_paragraph(doc, equation: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(equation.strip())
    run.font.name = "Cambria Math"
    run.font.size = Pt(12)


def _add_code_block(doc, code_lines: list[str]) -> None:
    from docx.shared import Pt
    for line in code_lines:
        p = doc.add_paragraph()
        run = p.add_run(line.rstrip())
        run.font.name = "Consolas"
        run.font.size = Pt(9)


def export_article_docx(article_text: str, title: str = "Journal Article Draft") -> tuple[io.BytesIO, str]:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", (title or "journal_article")[:80]).strip("_") or "journal_article"
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style.paragraph_format.line_spacing = 1.5

    table_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code = False
    equation_buffer: list[str] = []
    in_equation = False

    for raw_line in _finalise_article_text(article_text).splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            if in_code:
                _add_code_block(doc, code_buffer)
                code_buffer = []
                in_code = False
            else:
                if table_buffer:
                    _add_markdown_table(doc, table_buffer)
                    table_buffer = []
                in_code = True
            continue
        if in_code:
            code_buffer.append(line)
            continue

        stripped = line.strip()
        if stripped == "$$":
            if in_equation:
                _add_equation_paragraph(doc, " ".join(equation_buffer))
                equation_buffer = []
                in_equation = False
            else:
                if table_buffer:
                    _add_markdown_table(doc, table_buffer)
                    table_buffer = []
                in_equation = True
            continue
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            if table_buffer:
                _add_markdown_table(doc, table_buffer)
                table_buffer = []
            _add_equation_paragraph(doc, stripped.strip("$").strip())
            continue
        if in_equation:
            equation_buffer.append(stripped)
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_buffer.append(line)
            continue
        if table_buffer:
            _add_markdown_table(doc, table_buffer)
            table_buffer = []
        if not stripped:
            continue
        if line.startswith("# "):
            p = doc.add_heading(line[2:].strip(), level=0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=1)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=2)
        elif re.match(r"^[-*•]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            _add_inline_runs(p, re.sub(r"^[-*•]\s+", "", line).strip())
        elif re.match(r"^\d+[.)]\s+", line):
            p = doc.add_paragraph(style="List Number")
            _add_inline_runs(p, re.sub(r"^\d+[.)]\s+", "", line).strip())
        else:
            p = doc.add_paragraph()
            _add_inline_runs(p, line)
    if table_buffer:
        _add_markdown_table(doc, table_buffer)
    if code_buffer:
        _add_code_block(doc, code_buffer)
    if equation_buffer:
        _add_equation_paragraph(doc, " ".join(equation_buffer))

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream, f"{safe_title}_journal_article_draft.docx"
