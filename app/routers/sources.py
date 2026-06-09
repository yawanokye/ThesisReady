from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_conn, row_to_dict
from app.schemas import SourceSearchRequest
from app.source_finder import search_literature_sources

router = APIRouter(prefix="/api/projects", tags=["sources"])


def _source_key(src: dict[str, Any]) -> str:
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:100]
    return "title:" + title


def _merge_sources(existing: list[dict[str, Any]], new_sources: list[dict[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in [*(existing or []), *(new_sources or [])]:
        if not isinstance(src, dict):
            continue
        key = _source_key(src)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(src)
        if len(merged) >= limit:
            break
    return merged


def _source_notes(sources: list[dict[str, Any]], max_items: int = 20) -> str:
    lines = []
    for idx, src in enumerate(sources[:max_items], start=1):
        hint = src.get("apa_hint") or ""
        title = src.get("title") or "Untitled source"
        authors = src.get("authors") or []
        if isinstance(authors, list):
            authors = ", ".join(str(a) for a in authors[:4] if str(a).strip())
        year = src.get("year") or "n.d."
        doi = src.get("doi") or ""
        database = src.get("database") or ""
        if hint:
            lines.append(f"{idx}. {hint}")
        else:
            doi_text = f" DOI: {doi}." if doi else ""
            lines.append(f"{idx}. {authors} ({year}). {title}. {database}.{doi_text}")
    return "\n".join(lines)


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

    new_sources = result.get("sources") or []
    existing_sources = profile.get("source_bank") or []
    if not isinstance(existing_sources, list):
        existing_sources = []
    profile["source_bank"] = _merge_sources(existing_sources, new_sources)
    profile["retrieved_sources"] = result
    profile["source_search_terms"] = payload.query

    # Also keep human-readable notes so the drafting model can see the sources through both
    # structured source_bank and project-profile context. This enriches rather than replaces
    # user-pasted verified evidence.
    notes = str(profile.get("citation_evidence_notes") or "").strip()
    source_note_block = _source_notes(new_sources)
    if source_note_block:
        addition = "Retrieved literature sources attached to this project:\n" + source_note_block
        if addition not in notes:
            profile["citation_evidence_notes"] = (notes + "\n\n" + addition).strip() if notes else addition

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        "source_bank_count": len(profile.get("source_bank") or []),
        **result,
    }


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
