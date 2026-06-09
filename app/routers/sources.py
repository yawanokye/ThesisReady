from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_conn, row_to_dict
from app.schemas import SourceSearchRequest
from app.source_finder import search_literature_sources

router = APIRouter(prefix="/api/projects", tags=["sources"])


@router.post("/{project_id}/find-sources")
def find_sources(project_id: str, payload: SourceSearchRequest):
    project = _get_project_or_404(project_id)
    profile = project.get("profile", {})
    try:
        result = search_literature_sources(
            profile=profile,
            query=payload.query,
            max_results=payload.max_results,
            include_older_foundational=payload.include_older_foundational,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source search failed: {exc}") from exc

    profile["retrieved_sources"] = result
    profile["source_search_terms"] = payload.query

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        **result,
    }


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
