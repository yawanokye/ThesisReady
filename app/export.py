from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from docx import Document
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


def _add_runs_with_markup(paragraph, text: str) -> None:
    """Add text to a paragraph, colouring placeholders and revision additions red."""
    active_addition = False
    for segment in ADD_PATTERN.split(str(text or "")):
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
    paragraph = doc.add_paragraph()
    # This creates a Word OMML equation object. It is intentionally simple, but Word
    # treats it as an equation rather than plain paragraph text.
    safe = html.escape(equation or "")
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
