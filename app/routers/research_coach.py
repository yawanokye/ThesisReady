from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.database import get_conn, row_to_dict
from app.research_coach import coach
from app.schemas import ResearchCoachRequest

router = APIRouter(prefix="/api/research-coach", tags=["research-coach"])


def _project(project_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Research project not found.")
    return row_to_dict(row)


@router.post("")
def research_coach(payload: ResearchCoachRequest):
    if not str(payload.project_id or "").strip():
        raise HTTPException(status_code=422, detail="Connect a research project before using the project-aware Research Coach.")
    project = _project(payload.project_id.strip())
    return coach(project, payload.mode, payload.question)
