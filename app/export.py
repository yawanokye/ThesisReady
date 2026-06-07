from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt


def _split_blocks(markdown_text: str) -> list[str]:
    """Split markdown into logical blocks while keeping markdown tables together."""
    lines = (markdown_text or "").splitlines()
    blocks: list[str] = []
    current: list[str] = []
    in_table = False

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append("\n".join(current).strip())
            current = []

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")

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
        table.rows[0].cells[col_index].text = value

    for row_values in rows[1:]:
        cells = table.add_row().cells
        for col_index, value in enumerate(row_values):
            cells[col_index].text = value

    doc.add_paragraph("")


def _add_text_block(doc: Document, block: str) -> None:
    if block.startswith("### "):
        doc.add_heading(block.replace("#", "").strip(), level=3)
    elif block.startswith("## "):
        doc.add_heading(block.replace("#", "").strip(), level=2)
    elif block.startswith("# "):
        doc.add_heading(block.replace("#", "").strip(), level=1)
    else:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                doc.add_paragraph(stripped[2:], style="List Bullet")
            elif re.match(r"^\d+\.\s+", stripped):
                doc.add_paragraph(re.sub(r"^\d+\.\s+", "", stripped), style="List Number")
            else:
                doc.add_paragraph(stripped)


def export_chapter_docx(project: dict[str, Any], chapter_number: int, draft: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", project.get("title", "project"))[:60]
    path = out_dir / f"{safe_title}_chapter_{chapter_number}.docx"

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)

    doc.add_heading(project.get("title", "ProjectReady AI Draft"), level=0)
    doc.add_paragraph(f"Chapter {chapter_number} draft generated with ProjectReady AI.")
    doc.add_paragraph("Note: Verify all citations, evidence, data, page numbers, and supervisor requirements before submission.")

    for block in _split_blocks(draft):
        if _is_markdown_table(block):
            _add_markdown_table(doc, block)
        else:
            _add_text_block(doc, block)

    doc.save(path)
    return path


def export_compliance_docx(project: dict[str, Any], chapter_number: int, check: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", project.get("title", "project"))[:60]
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
        row[0].text = item.get("section_title", "")
        row[1].text = item.get("requirement", "")
        row[2].text = item.get("status", "")
        row[3].text = item.get("evidence", "")
        row[4].text = item.get("suggested_action", "")

    doc.save(path)
    return path
