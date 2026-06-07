from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_conn, row_to_dict
from app.schemas import ProjectCreate, SectionSelection

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create_project(payload: ProjectCreate):
    project_id = str(uuid.uuid4())
    profile = payload.model_dump()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, title, profile_json, selected_sections_json, drafts_json, checks_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, payload.title, json.dumps(profile), "{}", "{}", "{}"),
        )
        conn.commit()
    return {"id": project_id, "title": payload.title, "profile": profile}


@router.get("")
def list_projects():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [row_to_dict(row) for row in rows]


@router.get("/{project_id}")
def get_project(project_id: str):
    project = _get_project_or_404(project_id)
    return project


@router.post("/{project_id}/sections")
def save_section_selection(project_id: str, payload: SectionSelection):
    project = _get_project_or_404(project_id)
    selected = project.get("selected_sections", {})
    selected[str(payload.chapter_number)] = payload.selected_section_ids
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET selected_sections_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(selected), project_id),
        )
        conn.commit()
    return {"project_id": project_id, "selected_sections": selected}


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
