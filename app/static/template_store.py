from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).parent / "data" / "default_template.json"


def load_default_template() -> dict[str, Any]:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_chapters(template: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    template = template or load_default_template()
    return template.get("chapters", [])


def get_chapter(chapter_number: int, template: dict[str, Any] | None = None) -> dict[str, Any]:
    template = template or load_default_template()
    for chapter in template.get("chapters", []):
        if chapter.get("chapter_number") == chapter_number:
            return chapter
    raise KeyError(f"Chapter {chapter_number} not found")


def flatten_sections(chapter: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for group in chapter.get("section_groups", []):
        sections.extend(group.get("sections", []))
    return sections


def selected_sections(chapter_number: int, selected_ids: list[str]) -> list[dict[str, Any]]:
    chapter = get_chapter(chapter_number)
    all_sections = flatten_sections(chapter)
    if not selected_ids:
        return [s for s in all_sections if s.get("default_selected")]
    selected_set = set(selected_ids)
    return [s for s in all_sections if s.get("section_id") in selected_set]


def default_selected_ids(chapter_number: int) -> list[str]:
    chapter = get_chapter(chapter_number)
    return [s["section_id"] for s in flatten_sections(chapter) if s.get("default_selected")]
