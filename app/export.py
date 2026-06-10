from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt, RGBColor


PLACEHOLDER_PATTERN = re.compile(r"(\[[^\]\n]{3,}\])")
ADD_PATTERN = re.compile(r"(\[\[ADD\]\]|\[\[/ADD\]\])")
PLACEHOLDER_RED = RGBColor(180, 35, 24)
ADDITION_RED = RGBColor(180, 35, 24)

CHAPTER_LABELS = {
    1: "introduction_chapter",
    2: "literature_review_chapter",
    3: "research_methods_methodology_chapter",
    4: "results_data_analysis_discussion_chapter",
    5: "summary_conclusion_recommendation_chapter",
    6: "other_chapter",
}


SUBSCRIPT_MAP = str.maketrans("0123456789+-=()abcdefghijklmnopqrstuvwxyz", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐᵦ꜀ᑯₑբ₉ₕᵢⱼₖₗₘₙₒₚ૧ᵣₛₜᵤᵥwₓᵧ₂")
SUPERSCRIPT_MAP = str.maketrans("0123456789+-=()abcdefghijklmnopqrstuvwxyz", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖ۹ʳˢᵗᵘᵛʷˣʸᶻ")

GREEK_LATEX = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Delta": "Δ", "Gamma": "Γ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Omega": "Ω",
}

MATH_COMMANDS = {
    "sum": "∑", "times": "×", "cdot": "·", "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "infty": "∞", "pm": "±", "%": "%",
}


def _to_subscript(value: str) -> str:
    return str(value or "").translate(SUBSCRIPT_MAP)


def _to_superscript(value: str) -> str:
    return str(value or "").translate(SUPERSCRIPT_MAP)


def _latex_to_word_equation_text(equation: str) -> str:
    """Convert common LaTeX-style model notation into readable Word equation text.

    This does not try to be a full LaTeX engine. It handles the notation normally
    produced by the app for methods chapters, including Greek letters, subscripts,
    superscripts, sums, fractions and simple aligned equations. The text is then
    embedded in a Word OMML math object so it opens as an equation rather than as
    raw backslash-filled text.
    """
    text = str(equation or "")
    text = text.replace("\\begin{aligned}", "").replace("\\end{aligned}", "")
    text = text.replace("\\begin{align}", "").replace("\\end{align}", "")
    text = text.replace("\\begin{equation}", "").replace("\\end{equation}", "")
    text = text.replace("\\left", "").replace("\\right", "")
    text = text.replace("\\,", " ").replace("\\;", " ").replace("\\:", " ")
    text = re.sub(r"\\\\\s*", "\n", text)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)

    for name, symbol in {**GREEK_LATEX, **MATH_COMMANDS}.items():
        text = re.sub(rf"\\{name}\b", symbol, text)

    # Convert common subscript and superscript patterns after replacing commands.
    text = re.sub(r"_\{([^{}]+)\}", lambda m: _to_subscript(m.group(1)), text)
    text = re.sub(r"_([A-Za-z0-9+-=])", lambda m: _to_subscript(m.group(1)), text)
    text = re.sub(r"\^\{([^{}]+)\}", lambda m: _to_superscript(m.group(1)), text)
    text = re.sub(r"\^([A-Za-z0-9+-=])", lambda m: _to_superscript(m.group(1)), text)

    # Remove remaining LaTeX grouping and simple spacing commands.
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\ ", " ")
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_inline_latex_text(text: str) -> str:
    """Replace inline LaTeX markers such as \(PCR_i\) with readable text."""
    cleaned = re.sub(r"\\\((.*?)\\\)", lambda m: _latex_to_word_equation_text(m.group(1)), str(text or ""))
    cleaned = re.sub(r"\$([^$\n]+)\$", lambda m: _latex_to_word_equation_text(m.group(1)), cleaned)
    return cleaned


def _add_runs_with_markup(paragraph, text: str) -> None:
    """Add text to a paragraph, colouring placeholders and revision additions red."""
    text = _clean_inline_latex_text(str(text or ""))
    active_addition = False
    for segment in ADD_PATTERN.split(text):
        if not segment:
            continue
        if segment == "[[ADD]]":
            active_addition = True
            continue
        if segment == "[[/ADD]]":
            active_addition = False
            continue
        for part in PLACEHOLDER_PATTERN.split(segment):
            if not part:
                continue
            run = paragraph.add_run(part)
            if active_addition:
                run.font.color.rgb = ADDITION_RED
            if PLACEHOLDER_PATTERN.fullmatch(part):
                run.font.color.rgb = PLACEHOLDER_RED
                run.bold = True


def _set_cell_text_with_markup(cell, text: str) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    _add_runs_with_markup(paragraph, text)


def _split_blocks(markdown_text: str) -> list[str]:
    """Split markdown into logical blocks while keeping tables and equations together."""
    lines = (markdown_text or "").splitlines()
    blocks: list[str] = []
    current: list[str] = []
    in_table = False
    in_equation = False

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append("\n".join(current).strip())
            current = []

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        is_eq_marker = stripped == "$$" or (stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4)

        if stripped == "$$":
            if not in_equation:
                flush()
                in_equation = True
                current.append(line)
            else:
                current.append(line)
                flush()
                in_equation = False
            continue

        if in_equation:
            current.append(line)
            continue

        if is_eq_marker:
            flush()
            blocks.append(line.strip())
            continue

        if is_table_line:
            if current and not in_table:
                flush()
            in_table = True
            current.append(line)
            continue

        if in_table:
            flush()
            in_table = False

        if not stripped:
            flush()
        else:
            current.append(line)

    flush()
    return [block for block in blocks if block]


def _is_markdown_table(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    if not all(line.startswith("|") and line.endswith("|") for line in lines):
        return False
    separator = lines[1]
    return bool(re.match(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$", separator))


def _parse_markdown_table(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if index == 1 and re.match(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return []
    max_cols = max(len(row) for row in rows)
    return [row + [""] * (max_cols - len(row)) for row in rows]


def _add_markdown_table(doc: Document, block: str) -> None:
    rows = _parse_markdown_table(block)
    if not rows:
        return
    table = doc.add_table(rows=1, cols=len(rows[0]))
    table.style = "Table Grid"
    for col_index, value in enumerate(rows[0]):
        _set_cell_text_with_markup(table.rows[0].cells[col_index], value)
    for row_values in rows[1:]:
        cells = table.add_row().cells
        for col_index, value in enumerate(row_values):
            _set_cell_text_with_markup(cells[col_index], value)
    doc.add_paragraph("")


def _equation_from_block(block: str) -> str | None:
    stripped = block.strip()
    if stripped.startswith("$$") and stripped.endswith("$$"):
        return stripped.strip("$").strip()
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].strip() == "$$" and lines[-1].strip() == "$$":
        return "\n".join(lines[1:-1]).strip()
    return None


def _add_word_equation(doc: Document, equation: str) -> None:
    converted = _latex_to_word_equation_text(equation)
    for line in [ln.strip() for ln in converted.splitlines() if ln.strip()]:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        safe = html.escape(line)
        omath = parse_xml(f'<m:oMath {nsdecls("m") }><m:r><m:t>{safe}</m:t></m:r></m:oMath>')
        paragraph._p.append(omath)


def _add_text_block(doc: Document, block: str) -> None:
    if block.startswith("### "):
        paragraph = doc.add_heading("", level=3)
        _add_runs_with_markup(paragraph, block.replace("#", "").strip())
    elif block.startswith("## "):
        paragraph = doc.add_heading("", level=2)
        _add_runs_with_markup(paragraph, block.replace("#", "").strip())
    elif block.startswith("# "):
        paragraph = doc.add_heading("", level=1)
        _add_runs_with_markup(paragraph, block.replace("#", "").strip())
    else:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                paragraph = doc.add_paragraph(style="List Bullet")
                _add_runs_with_markup(paragraph, stripped[2:])
            elif re.match(r"^\d+\.\s+", stripped):
                paragraph = doc.add_paragraph(style="List Number")
                _add_runs_with_markup(paragraph, re.sub(r"^\d+\.\s+", "", stripped))
            else:
                paragraph = doc.add_paragraph()
                _add_runs_with_markup(paragraph, stripped)


def _safe_title(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value or "project")[:60]


def export_chapter_docx(project: dict[str, Any], chapter_number: int, draft: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _safe_title(project.get("title", "project"))
    label = CHAPTER_LABELS.get(chapter_number, f"chapter_{chapter_number}")
    path = out_dir / f"{safe_title}_{label}.docx"

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)

    doc.add_heading(project.get("title", "ProjectReady AI Draft"), level=0)
    doc.add_paragraph("Draft generated based on the information provided.")
    doc.add_paragraph("Note: Verify all citations, evidence, data, equations, reference entries, page numbers, and supervisor requirements before submission.")

    for block in _split_blocks(draft):
        equation = _equation_from_block(block)
        if equation:
            _add_word_equation(doc, equation)
        elif _is_markdown_table(block):
            _add_markdown_table(doc, block)
        else:
            _add_text_block(doc, block)

    doc.save(path)
    return path


def export_compliance_docx(project: dict[str, Any], chapter_number: int, check: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _safe_title(project.get("title", "project"))
    path = out_dir / f"{safe_title}_chapter_{chapter_number}_compliance.docx"

    doc = Document()
    doc.add_heading("ProjectReady AI Compliance Report", level=0)
    doc.add_paragraph(f"Project: {project.get('title', '')}")
    doc.add_paragraph(f"Chapter: {chapter_number}")
    doc.add_paragraph(f"Compliance score: {check.get('score_percent', 0)}%")

    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Section"
    hdr[1].text = "Requirement"
    hdr[2].text = "Status"
    hdr[3].text = "Evidence"
    hdr[4].text = "Suggested action"

    for item in check.get("items", []):
        row = table.add_row().cells
        _set_cell_text_with_markup(row[0], item.get("section_title", ""))
        _set_cell_text_with_markup(row[1], item.get("requirement", ""))
        _set_cell_text_with_markup(row[2], item.get("status", ""))
        _set_cell_text_with_markup(row[3], item.get("evidence", ""))
        _set_cell_text_with_markup(row[4], item.get("suggested_action", ""))

    doc.save(path)
    return path


def export_instrument_docx(project: dict[str, Any], chapter_number: int, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = project.get("profile", {}) or {}
    title = project.get("title") or profile.get("title") or "ProjectReady AI"
    safe_title = _safe_title(title)
    path = out_dir / f"{safe_title}_draft_research_instrument.docx"

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)

    approach = str(profile.get("research_approach") or "Quantitative").lower()
    data_type = str(profile.get("data_type") or "Primary survey data").lower()
    objectives = _profile_objectives(profile)
    constructs = _profile_constructs(profile, objectives)

    doc.add_heading("Draft Research Instrument", level=0)
    doc.add_paragraph(f"Study title: {title}")
    doc.add_paragraph(
        "Draft generated based on the project title, objectives and supplied constructs/variables. "
        "The student must review the items, align them with validated scales where required, pilot the instrument, and obtain supervisor or ethics approval before data collection."
    )

    include_questionnaire = "quant" in approach or "survey" in data_type or "primary" in data_type or "mixed" in approach or "mixed" in data_type
    include_interview = "qual" in approach or "interview" in data_type or "mixed" in approach or "mixed" in data_type

    if include_questionnaire:
        _add_questionnaire(doc, objectives, constructs)
    if include_interview:
        _add_interview_guide(doc, objectives, constructs)
    if not include_questionnaire and not include_interview:
        _add_questionnaire(doc, objectives, constructs)

    doc.save(path)
    return path


def _profile_objectives(profile: dict[str, Any]) -> list[str]:
    objectives = profile.get("objectives") or []
    if isinstance(objectives, str):
        objectives = [obj.strip() for obj in re.split(r"\n|;", objectives) if obj.strip()]
    return [str(obj).strip() for obj in objectives if str(obj).strip()]


def _profile_constructs(profile: dict[str, Any], objectives: list[str]) -> list[str]:
    variables = profile.get("variables") or {}
    raw: list[str] = []
    if isinstance(variables, dict):
        for key in ["raw_variables", "constructs", "variables", "iv", "dv", "mediator", "moderator", "controls"]:
            value = variables.get(key)
            if isinstance(value, list):
                raw.extend(str(v).strip() for v in value if str(v).strip())
            elif isinstance(value, str):
                raw.extend(x.strip() for x in re.split(r"\n|;|,", value) if x.strip())
    elif isinstance(variables, list):
        raw.extend(str(v).strip() for v in variables if str(v).strip())

    title = str(profile.get("title") or "")
    research_area = str(profile.get("research_area") or "")
    text = " ".join([title, research_area, " ".join(objectives)])

    # Extract phrases commonly used in objectives and titles.
    patterns = [
        r"relationship between ([^.;]+?) and ([^.;]+?)(?: among| in | of |$)",
        r"effect of ([^.;]+?) on ([^.;]+?)(?: among| in | of |$)",
        r"influence of ([^.;]+?) on ([^.;]+?)(?: among| in | of |$)",
        r"impact of ([^.;]+?) on ([^.;]+?)(?: among| in | of |$)",
        r"mediating role of ([^.;:]+?)(?: among| in | on |$)",
        r"moderating role of ([^.;:]+?)(?: among| in | on |$)",
        r"level of ([^.;]+?)(?: among| in | of |$)",
    ]
    for pat in patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            raw.extend(part.strip() for part in match.groups() if part and part.strip())

    # Title pattern: X and Y: Mediating Role of Z
    if ":" in title:
        before, after = title.split(":", 1)
        raw.extend(x.strip() for x in re.split(r"\band\b|,", before, flags=re.IGNORECASE) if x.strip())
        m = re.search(r"role of\s+(.+)$", after, flags=re.IGNORECASE)
        if m:
            raw.append(m.group(1).strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    stop = {"study", "students", "undergraduate students", "selected private institutions", "ghana", "relationship", "effect", "impact", "influence", "role"}
    for item in raw:
        item = re.sub(r"\b(among|in|of|on|with|the|a|an)\b.*$", lambda m: "" if m.group(1).lower() in {"among", "in"} else m.group(0), item, flags=re.IGNORECASE).strip()
        item = re.sub(r"\s+", " ", item).strip(" .,:;-")
        if not item or len(item) < 3:
            continue
        if item.lower() in stop:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(item)
    if not cleaned:
        cleaned = ["[insert construct/variable 1]", "[insert construct/variable 2]"]
    return cleaned[:8]


def _item_bank_for_construct(construct: str) -> list[str]:
    c = construct.lower()
    if "regret" in c:
        return [
            "I feel that choosing this institution/programme may not have been the best decision for me.",
            "I sometimes think that another institution/programme would have suited me better.",
            "I feel disappointed when I compare my current institution/programme with alternatives I considered.",
            "I have questioned whether my enrolment decision was the right one.",
            "Looking back, I would have considered a different institution/programme more seriously."
        ]
    if "dissatisfaction" in c or "satisfaction" in c:
        return [
            "I am dissatisfied with important aspects of my experience in this institution/programme.",
            "The institution/programme has not met my expectations in several important areas.",
            "I am dissatisfied with the quality of support or services available to students.",
            "My overall experience in this institution/programme has been below what I expected.",
            "I would hesitate to describe my experience in this institution/programme as satisfactory."
        ]
    if "expectation" in c:
        return [
            "My expectations before enrolment were clear and specific.",
            "The institution/programme has fulfilled the expectations I had before enrolment.",
            "There is a gap between what I expected and what I have experienced.",
            "The information I received before enrolment shaped my expectations about this institution/programme.",
            "My expectations about academic support, facilities and future opportunities have influenced my evaluation of the institution/programme."
        ]
    if "quality" in c:
        return [
            f"The {construct} experienced in this context is satisfactory.",
            f"The institution/organisation provides reliable {construct}.",
            f"The {construct} meets the needs of relevant stakeholders.",
            f"There are noticeable weaknesses in {construct}.",
            f"Improvements in {construct} would enhance overall outcomes."
        ]
    return [
        f"The issues represented by {construct} are evident in the study context.",
        f"{construct} influences experiences, decisions or outcomes in the study context.",
        f"Respondents can clearly evaluate {construct} based on their experience.",
        f"There are important differences in how respondents experience {construct}.",
        f"Improvement in {construct} would contribute to better outcomes in the study context."
    ]


def _add_questionnaire(doc: Document, objectives: list[str], constructs: list[str]) -> None:
    doc.add_heading("Draft Questionnaire", level=1)
    doc.add_paragraph(
        "Introductory statement: This questionnaire is designed to collect data for academic research. "
        "Participation is voluntary, responses will be treated confidentially, and no personally identifying information should be reported unless the approved protocol requires it."
    )

    doc.add_heading("Section A: Background Information", level=2)
    demographics = ["Gender", "Age group", "Level/year of study", "Programme/department", "Institution or organisation", "Mode of study/work", "Other study-specific background variable"]
    for item in demographics:
        doc.add_paragraph(f"{item}: [insert response options]", style="List Bullet")

    doc.add_heading("Section B: Main Study Constructs", level=2)
    doc.add_paragraph("Suggested response scale: 1 = Strongly disagree, 2 = Disagree, 3 = Neutral, 4 = Agree, 5 = Strongly agree. Reverse-coded items should be marked during instrument validation.")

    for idx, construct in enumerate(constructs, 1):
        doc.add_heading(f"Construct {idx}: {construct}", level=3)
        for number, item in enumerate(_item_bank_for_construct(construct), 1):
            doc.add_paragraph(f"{construct} {number}: {item}", style="List Number")

    doc.add_heading("Section C: Objective Alignment Matrix", level=2)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Objective"
    hdr[1].text = "Construct/Variable"
    hdr[2].text = "Suggested Instrument Section"
    hdr[3].text = "Validation Required"
    if not objectives:
        objectives = ["[insert objective 1]"]
    for idx, objective in enumerate(objectives, 1):
        row = table.add_row().cells
        row[0].text = objective
        row[1].text = ", ".join(constructs[:3]) if constructs else "[insert construct]"
        row[2].text = "Section B"
        row[3].text = "Expert review, pilot testing, reliability and construct validity checks"

    doc.add_heading("Instrument Validation Notes", level=2)
    for note in [
        "Replace generic items with validated or adapted scale items where the literature provides suitable measures.",
        "Submit the draft to experts for content validity review.",
        "Pilot the instrument with a small group similar to the target respondents.",
        "Check reliability using Cronbach's alpha or composite reliability where appropriate.",
        "Assess construct validity through EFA, CFA, PLS-SEM or another method aligned with the study design.",
        "Use procedural remedies for common method variance, including anonymity, clear item wording, varied item order and psychological separation of predictor and outcome items where appropriate.",
    ]:
        doc.add_paragraph(note, style="List Bullet")


def _add_interview_guide(doc: Document, objectives: list[str], constructs: list[str]) -> None:
    doc.add_heading("Draft Interview Guide", level=1)
    doc.add_paragraph("Opening statement: Thank the participant, explain the purpose of the study, confirm consent, remind the participant of confidentiality, and request permission to take notes or record where ethics approval allows.")

    doc.add_heading("Introductory Questions", level=2)
    for question in [
        "Please describe your background in relation to the topic under study.",
        "What experiences or observations make this topic important in your context?",
    ]:
        doc.add_paragraph(question, style="List Number")

    doc.add_heading("Core Questions by Objective and Construct", level=2)
    if not objectives:
        objectives = ["[insert objective 1]", "[insert objective 2]"]
    for idx, objective in enumerate(objectives, 1):
        related_constructs = ", ".join(constructs[:4]) if constructs else "[insert related construct]"
        doc.add_heading(f"Objective {idx}: {objective}", level=3)
        doc.add_paragraph(f"Main question: Based on your experience, how would you describe {related_constructs} in relation to this objective?", style="List Number")
        doc.add_paragraph("Probe 1: Can you give a specific example?", style="List Bullet")
        doc.add_paragraph("Probe 2: What factors explain this experience or outcome?", style="List Bullet")
        doc.add_paragraph("Probe 3: How has this affected people, institutions, decisions or processes involved?", style="List Bullet")
        doc.add_paragraph("Probe 4: What changes would you recommend?", style="List Bullet")

    doc.add_heading("Closing Questions", level=2)
    for question in [
        "Is there anything important about this topic that we have not discussed?",
        "What recommendations would you suggest based on your experience?",
    ]:
        doc.add_paragraph(question, style="List Number")


def export_methods_supplement_docx(project: dict[str, Any], chapter_number: int, out_dir: Path) -> Path:
    """Export a separate supplementary methods chapter for research instruments and data sources.

    This file is intentionally separate from the main Research Methods/Methodology chapter.
    It helps the student document questionnaire/interview-guide development, validated scale
    sources, secondary-data sources and appendix materials without overloading Chapter Three.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = project.get("profile", {}) or {}
    title = project.get("title") or profile.get("title") or "ProjectReady AI"
    safe_title = _safe_title(title)
    path = out_dir / f"{safe_title}_supplementary_methods_instrument_data_sources.docx"

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)

    approach = str(profile.get("research_approach") or "").lower()
    data_type = str(profile.get("data_type") or "").lower()
    objectives = _profile_objectives(profile)
    constructs = _profile_constructs(profile, objectives)
    sources = _profile_source_bank(profile)

    doc.add_heading("Supplementary Methods Chapter", level=0)
    doc.add_heading("Research Instrument and Data Source Specification", level=1)
    doc.add_paragraph(f"Study title: {title}")
    doc.add_paragraph(
        "This supplementary chapter supports the Research Methods/Methodology chapter. It documents the proposed research "
        "instrument, scale or item sources, variable measurement decisions, data-source traceability and appendix materials. "
        "It should be reviewed against supervisor comments, ethical approval conditions and the final institutional format before use."
    )

    _add_objective_construct_matrix(doc, objectives, constructs)

    include_primary = any(key in data_type for key in ["primary", "survey"]) or any(key in approach for key in ["quantitative", "qualitative", "mixed"])
    include_qual = "qual" in approach or "mixed" in approach or "qual" in data_type
    include_secondary = any(key in data_type for key in ["secondary", "econometric", "time-series", "panel"])

    if include_primary or not include_secondary:
        _add_instrument_development_sources(doc, objectives, constructs, sources)
        if "quant" in approach or "survey" in data_type or "primary" in data_type or "mixed" in approach:
            _add_questionnaire(doc, objectives, constructs)
        if include_qual:
            _add_interview_guide(doc, objectives, constructs)

    if include_secondary:
        _add_secondary_data_source_chapter(doc, objectives, constructs, sources)

    _add_appendix_guidance(doc, include_primary=include_primary, include_secondary=include_secondary)
    _add_supplement_reference_notes(doc, sources)

    doc.save(path)
    return path


def _profile_source_bank(profile: dict[str, Any]) -> list[dict[str, Any]]:
    sources = profile.get("source_bank") or []
    retrieved = profile.get("retrieved_sources") or {}
    if isinstance(retrieved, dict):
        sources = [*sources, *(retrieved.get("sources") or [])]
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        if not isinstance(src, dict):
            continue
        doi = str(src.get("doi") or "").strip().lower()
        title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:90]
        key = doi or title
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(src)
    return cleaned[:40]


def _match_sources_for_construct(construct: str, sources: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    terms = {t for t in re.findall(r"[A-Za-z]{4,}", str(construct).lower()) if t not in {"student", "students", "study", "effect", "role", "relationship", "among"}}
    ranked: list[tuple[int, dict[str, Any]]] = []
    for src in sources:
        haystack = " ".join([
            str(src.get("title") or ""),
            str(src.get("abstract") or ""),
            str(src.get("apa_hint") or ""),
            str(src.get("source") or ""),
        ]).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            ranked.append((score, src))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [src for _, src in ranked[:limit]]


def _format_source_hint(src: dict[str, Any]) -> str:
    hint = src.get("apa_hint") or src.get("reference_entry_hint") or ""
    if hint:
        return str(hint)
    authors = src.get("authors") or []
    if isinstance(authors, list):
        author_text = ", ".join(str(a) for a in authors[:3])
    else:
        author_text = str(authors or "[Author]")
    year = src.get("year") or "n.d."
    title = src.get("title") or "[Title]"
    source = src.get("source") or src.get("database") or ""
    doi = src.get("doi") or ""
    return " ".join(str(x) for x in [author_text, f"({year}).", title + ".", source, f"https://doi.org/{doi}" if doi else ""] if str(x).strip())


def _add_objective_construct_matrix(doc: Document, objectives: list[str], constructs: list[str]) -> None:
    doc.add_heading("Objective, Construct and Measurement Alignment", level=2)
    doc.add_paragraph("This matrix links the objectives to the constructs or variables that should guide questionnaire items, interview questions or secondary-data indicators.")
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for idx, label in enumerate(["Research Objective", "Construct/Variable", "Expected Evidence", "Measurement/Data Note"]):
        hdr[idx].text = label
    if not objectives:
        objectives = ["[insert research objective]"]
    for i, obj in enumerate(objectives):
        row = table.add_row().cells
        _set_cell_text_with_markup(row[0], obj)
        _set_cell_text_with_markup(row[1], constructs[i % len(constructs)] if constructs else "[insert construct/variable]")
        _set_cell_text_with_markup(row[2], "[insert questionnaire items, interview probes or secondary-data indicator aligned with this objective]")
        _set_cell_text_with_markup(row[3], "[state scale, coding, data source, frequency or validation requirement]")


def _add_instrument_development_sources(doc: Document, objectives: list[str], constructs: list[str], sources: list[dict[str, Any]]) -> None:
    doc.add_heading("Instrument Development and Source Traceability", level=2)
    doc.add_paragraph(
        "The table below identifies the constructs that should be measured and the source evidence that may support item development. "
        "Where no suitable source has been retrieved or supplied, the placeholder should be replaced with a validated scale, adapted instrument source or supervisor-approved item-development note."
    )
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    headers = ["Construct/Variable", "Objective Link", "Proposed Measurement", "Potential Scale/Item Source", "Required Action"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    if not constructs:
        constructs = ["[insert construct/variable]"]
    for idx, construct in enumerate(constructs, 1):
        matched = _match_sources_for_construct(construct, sources)
        source_text = "; ".join(_format_source_hint(src) for src in matched) if matched else "[insert validated or adapted scale/item source for this construct]"
        row = table.add_row().cells
        _set_cell_text_with_markup(row[0], construct)
        _set_cell_text_with_markup(row[1], objectives[(idx - 1) % len(objectives)] if objectives else "[insert linked objective]")
        _set_cell_text_with_markup(row[2], "Likert-scale items, index score, observed indicator or interview prompts, depending on design")
        _set_cell_text_with_markup(row[3], source_text)
        _set_cell_text_with_markup(row[4], "Adapt items, cite source, conduct expert review, pilot test and report reliability/validity evidence")


def _add_secondary_data_source_chapter(doc: Document, objectives: list[str], constructs: list[str], sources: list[dict[str, Any]]) -> None:
    doc.add_heading("Secondary Data and Variable Source Specification", level=2)
    doc.add_paragraph(
        "For secondary-data, econometric, time-series or panel-data studies, this section should document the exact data source, variable construction, frequency, transformation and verification procedure for each variable."
    )
    table = doc.add_table(rows=1, cols=8)
    table.style = "Table Grid"
    headers = ["Objective", "Variable", "Operational Definition", "Preferred Data Source", "Coverage/Frequency", "Transformation/Coding", "Quality Check", "Appendix Material"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    if not constructs:
        constructs = ["[insert dependent variable]", "[insert independent variable]", "[insert control variable]"]
    if not objectives:
        objectives = ["[insert objective]"]
    for idx, variable in enumerate(constructs):
        matched = _match_sources_for_construct(variable, sources, limit=2)
        source_hint = "; ".join(_format_source_hint(src) for src in matched) if matched else "[insert official data source, database, report or institutional record]"
        row = table.add_row().cells
        _set_cell_text_with_markup(row[0], objectives[idx % len(objectives)])
        _set_cell_text_with_markup(row[1], variable)
        _set_cell_text_with_markup(row[2], "[define how the variable is measured or computed]")
        _set_cell_text_with_markup(row[3], source_hint)
        _set_cell_text_with_markup(row[4], "[insert country/firm/sample coverage and frequency]")
        _set_cell_text_with_markup(row[5], "[insert log, differencing, scaling, index construction or coding]")
        _set_cell_text_with_markup(row[6], "[insert missing-data, outlier, unit-root, stationarity or consistency checks]")
        _set_cell_text_with_markup(row[7], "Data dictionary, extraction log, raw data sample and codebook")


def _add_appendix_guidance(doc: Document, include_primary: bool, include_secondary: bool) -> None:
    doc.add_heading("Appendix Placement Guide", level=2)
    notes = []
    if include_primary:
        notes.extend([
            "Full questionnaire or interview guide should normally appear in the appendix after ethical approval is obtained.",
            "Expert review forms, pilot-test feedback and consent scripts may be placed in the appendix where the institution requires them.",
            "Full item wording, coding scheme and reverse-coded item notes should be retained in the appendix or instrument file.",
        ])
    if include_secondary:
        notes.extend([
            "Raw data extracts, detailed codebooks, transformation logs and variable construction formulas should normally be placed in the appendix.",
            "Lengthy diagnostic outputs, robustness checks, correlation matrices and software logs should be summarised in the main chapter and placed fully in the appendix.",
        ])
    if not notes:
        notes.append("Place lengthy technical materials in the appendix and keep the main methodology chapter focused on defensible methodological explanation.")
    for note in notes:
        doc.add_paragraph(note, style="List Bullet")


def _add_supplement_reference_notes(doc: Document, sources: list[dict[str, Any]]) -> None:
    doc.add_heading("Potential References and Source Notes", level=2)
    if not sources:
        paragraph = doc.add_paragraph()
        _add_runs_with_markup(paragraph, "[insert APA references for validated instruments, data sources, methodological guidance or official datasets used in this supplementary chapter]")
        return
    for src in sources[:20]:
        paragraph = doc.add_paragraph(style="List Bullet")
        _add_runs_with_markup(paragraph, _format_source_hint(src))
