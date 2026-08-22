from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.data_analysis import (
    list_datasets,
    list_runs,
    load_dataset,
    method_catalog,
    recommend_analysis,
    run_analysis,
    save_dataset,
)
from app.database import get_conn, row_to_dict
from app.qualitative_analysis import code_transcript, integration_matrix, parse_codebook
from app.research_journey import research_record
from app.result_uploads import extract_result_file

router = APIRouter(prefix="/api/data-analysis", tags=["data-analysis"])


def _project(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Research project not found.")
    return project


def _save_profile(project_id: str, profile: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(profile), project_id))
        conn.commit()


@router.post("/{project_id}/datasets")
async def upload_dataset(project_id: str, file: UploadFile = File(...)):
    _project(project_id)
    content = await file.read()
    try:
        return save_dataset(project_id, file.filename or "dataset.csv", content)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{project_id}/datasets")
def datasets(project_id: str):
    _project(project_id)
    return {"datasets": list_datasets(project_id)}


@router.get("/{project_id}/datasets/{dataset_id}/profile")
def dataset_profile(project_id: str, dataset_id: str):
    project = _project(project_id)
    try:
        df, item = load_dataset(project_id, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    profile = project.get("profile") or {}
    rec = research_record(profile, str(project.get("title") or ""))
    framework = str(profile.get("conceptual_framework_summary") or "")
    return {
        "dataset": {"id": dataset_id, "filename": item.get("filename"), "rows": int(len(df)), "columns": [str(c) for c in df.columns]},
        "research_record": rec,
        "recommendations": recommend_analysis({}, rec.get("logic", {}).get("objectives") or [], framework),
        "conceptual_framework_optional": True,
        "note": "The conceptual framework can guide variable roles and path selection, but analysis can proceed without it when the objectives, design and data structure are sufficient.",
    }


@router.get("/methods/catalog")
def analysis_method_catalog():
    return {
        "methods": method_catalog(),
        "principle": "Every method is paired with its variants, assumptions and diagnostics. Optional specialist runtimes fail closed rather than being approximated by another model.",
    }


@router.post("/{project_id}/recommend")
def recommend(project_id: str, payload: dict[str, Any]):
    project = _project(project_id)
    profile = project.get("profile") or {}
    objectives = payload.get("objectives") if isinstance(payload.get("objectives"), list) else (profile.get("objectives") or [])
    framework = str(payload.get("conceptual_framework_summary") or profile.get("conceptual_framework_summary") or "")
    return {"recommendations": recommend_analysis({}, [str(x) for x in objectives], framework), "conceptual_framework_optional": True}


@router.post("/{project_id}/framework")
def save_framework(project_id: str, payload: dict[str, Any]):
    project = _project(project_id)
    profile = project.get("profile") or {}
    profile["conceptual_framework_summary"] = str(payload.get("summary") or "").strip()[:10000]
    paths = payload.get("paths") if isinstance(payload.get("paths"), list) else []
    profile["conceptual_framework_paths"] = paths[:100]
    _save_profile(project_id, profile)
    return {"ok": True, "summary": profile["conceptual_framework_summary"], "paths": profile["conceptual_framework_paths"], "optional": True}


@router.post("/{project_id}/run")
def calculate(project_id: str, payload: dict[str, Any]):
    project = _project(project_id)
    dataset_id = str(payload.get("dataset_id") or "").strip()
    if not dataset_id:
        raise HTTPException(status_code=422, detail="Select an uploaded dataset before running analysis.")
    spec = payload.get("specification") if isinstance(payload.get("specification"), dict) else payload
    try:
        result = run_analysis(project_id, dataset_id, spec, (project.get("profile") or {}).get("objectives") or [])
    except (ValueError, RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = project.get("profile") or {}
    summaries = profile.get("analysis_run_summaries") if isinstance(profile.get("analysis_run_summaries"), list) else []
    summaries.append({"run_id": result.get("run_id"), "analysis": result.get("analysis"), "objective": (result.get("objective_alignment") or {}).get("objective"), "dataset_id": dataset_id})
    profile["analysis_run_summaries"] = summaries[-100:]
    _save_profile(project_id, profile)
    return result


@router.get("/{project_id}/runs")
def runs(project_id: str):
    _project(project_id)
    return {"runs": list_runs(project_id)}


@router.post("/{project_id}/qualitative/code")
async def qualitative_code(
    project_id: str,
    file: UploadFile = File(...),
    codebook: str = Form(...),
):
    _project(project_id)
    content = await file.read()
    try:
        extracted = extract_result_file(file.filename or "transcript.txt", content)
        codes = parse_codebook(codebook)
        if not codes:
            raise ValueError("Provide at least one researcher-defined code and keyword set.")
        result = code_transcript(str(extracted.get("extracted_text") or ""), codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["filename"] = file.filename
    result["traceability_note"] = "Every suggested code remains linked to the actual uploaded transcript excerpt. ProjectReady does not invent quotations or themes."
    return result


@router.post("/{project_id}/mixed-methods/integration")
def mixed_integration(project_id: str, payload: dict[str, Any]):
    _project(project_id)
    quantitative = payload.get("quantitative_findings") if isinstance(payload.get("quantitative_findings"), list) else []
    qualitative = payload.get("qualitative_themes") if isinstance(payload.get("qualitative_themes"), list) else []
    return integration_matrix(quantitative, qualitative)
