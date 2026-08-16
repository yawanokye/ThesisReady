from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.database import get_conn, row_to_dict, save_draft_version
from app.schemas import (
    ClaimCitationApplyRequest,
    ClaimSupportIgnoreRequest,
    ClaimSourceApprovalRequest,
    ClaimSourceSearchRequest,
    SelectedPaperMetadataUpdate,
    SourceSearchRequest,
)
from app.source_finder import search_literature_sources
from app.claim_support_review import (
    apply_approved_claim_citations,
    build_claim_support_review,
    merge_source_into_bank,
    public_candidate,
    remove_review_item_placeholder,
)
from app.citation_matrix import remove_unverified_generated_citations
from app.selected_papers import (
    MAX_SELECTED_PAPERS,
    MAX_SELECTED_PAPERS_TOTAL_BYTES,
    build_selected_paper_record,
    public_paper_record,
    public_source_bank,
    sync_selected_papers_to_source_bank,
    update_selected_paper_metadata,
)

router = APIRouter(prefix="/api/projects", tags=["sources"])


def _source_key(src: dict[str, Any]) -> str:
    doi = str(src.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    title = re.sub(r"[^a-z0-9]+", "", str(src.get("title") or "").lower())[:100]
    return "title:" + title


def _merge_sources(existing: list[dict[str, Any]], new_sources: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
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


def _source_notes(sources: list[dict[str, Any]], max_items: int = 30) -> str:
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
        tier = src.get("relevance_tier") or "unclassified"
        reason = src.get("relevance_reason") or "No relevance explanation supplied."
        use = src.get("suggested_use") or "Use only where it directly supports the claim."
        prefix = f"{idx}. [{tier}] "
        suffix = f" Relevance: {reason} Suggested use: {use}"
        if hint:
            lines.append(prefix + f"{hint}." + suffix)
        else:
            doi_text = f" DOI: {doi}." if doi else ""
            lines.append(prefix + f"{authors} ({year}). {title}. {database}.{doi_text}" + suffix)
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
            use_relevance_gate=payload.use_relevance_gate,
            attach_not_relevant_sources=payload.attach_not_relevant_sources,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source search failed: {exc}") from exc

    new_sources = result.get("sources") or []
    existing_sources = profile.get("source_bank") or []
    if not isinstance(existing_sources, list):
        existing_sources = []

    # Replace earlier automated search results so a refined search also removes
    # stale unrelated records. Preserve only sources explicitly marked as manual
    # or user-verified.
    preserved_sources = [
        src for src in existing_sources
        if isinstance(src, dict) and (
            bool(src.get("user_verified"))
            or str(src.get("attachment_origin") or "") in {"manual", "uploaded", "user_verified", "uploaded_selected_paper"}
        )
    ]
    profile["source_bank"] = _merge_sources(preserved_sources, new_sources)
    profile["retrieved_sources"] = result
    profile["source_search_terms"] = payload.query

    # Refresh, rather than append to, the machine-generated source-note block.
    # This prevents unrelated records from an earlier search remaining in the
    # prompt after the user refines the query.
    marker = "Retrieved literature sources attached to this project:"
    notes = str(profile.get("citation_evidence_notes") or "").strip()
    if marker in notes:
        notes = notes.split(marker, 1)[0].rstrip()
    source_note_block = _source_notes(new_sources)
    if source_note_block:
        addition = marker + "\n" + source_note_block
        profile["citation_evidence_notes"] = (notes + "\n\n" + addition).strip() if notes else addition
    else:
        profile["citation_evidence_notes"] = notes

    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        "source_bank_count": len(profile.get("source_bank") or []),
        "attached_count_this_search": len(new_sources),
        "source_bank": profile.get("source_bank") or [],
        **result,
    }


def _save_profile(project_id: str, profile: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(profile), project_id),
        )
        conn.commit()


def _selected_paper_summaries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    papers = profile.get("selected_papers") or []
    if not isinstance(papers, list):
        return []
    return [public_paper_record(item) for item in papers if isinstance(item, dict)]


@router.get("/{project_id}/selected-papers")
def list_selected_papers(project_id: str) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    papers = _selected_paper_summaries(profile)
    return {
        "project_id": project_id,
        "papers": papers,
        "count": len(papers),
        "maximum": MAX_SELECTED_PAPERS,
        "capacity_remaining": max(0, MAX_SELECTED_PAPERS - len(papers)),
        "citation_ready": sum(1 for item in papers if item.get("citation_eligible")),
        "needs_metadata_confirmation": sum(1 for item in papers if not item.get("citation_eligible")),
    }


@router.post("/{project_id}/selected-papers")
async def upload_selected_papers(
    project_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    existing = profile.get("selected_papers") or []
    if not isinstance(existing, list):
        existing = []
    incoming = [file for file in files if file and file.filename]
    if not incoming:
        raise HTTPException(status_code=400, detail="Choose at least one paper to upload.")
    if len(existing) + len(incoming) > MAX_SELECTED_PAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"A project can contain up to {MAX_SELECTED_PAPERS} selected papers. Remove some papers or upload fewer files.",
        )

    uploaded: list[dict[str, Any]] = []
    skipped_duplicates: list[str] = []
    errors: list[dict[str, str]] = []
    existing_keys = {
        (str(item.get("doi") or "").strip().lower() or str(item.get("filename") or "").strip().lower())
        for item in existing if isinstance(item, dict)
    }
    total_bytes = 0
    for file in incoming:
        try:
            content = await file.read()
            total_bytes += len(content)
            if total_bytes > MAX_SELECTED_PAPERS_TOTAL_BYTES:
                raise ValueError(f"The combined selected-paper upload exceeds the {MAX_SELECTED_PAPERS_TOTAL_BYTES // (1024 * 1024)} MB request limit.")
            record = build_selected_paper_record(file.filename or "selected-paper", content)
            key = str(record.get("doi") or "").strip().lower() or str(record.get("filename") or "").strip().lower()
            if key and key in existing_keys:
                skipped_duplicates.append(record.get("filename") or file.filename or "paper")
                continue
            if key:
                existing_keys.add(key)
            existing.append(record)
            uploaded.append(record)
        except ValueError as exc:
            errors.append({"filename": file.filename or "paper", "error": str(exc)})
        except Exception as exc:
            errors.append({"filename": file.filename or "paper", "error": f"Could not process this paper: {str(exc)[:200]}"})

    profile["selected_papers"] = existing[:MAX_SELECTED_PAPERS]
    source_bank = sync_selected_papers_to_source_bank(profile)
    _save_profile(project_id, profile)
    papers = _selected_paper_summaries(profile)
    return {
        "project_id": project_id,
        "papers": papers,
        "count": len(papers),
        "maximum": MAX_SELECTED_PAPERS,
        "capacity_remaining": max(0, MAX_SELECTED_PAPERS - len(papers)),
        "uploaded_count": len(uploaded),
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
        "citation_ready": sum(1 for item in papers if item.get("citation_eligible")),
        "needs_metadata_confirmation": sum(1 for item in papers if not item.get("citation_eligible")),
        "source_bank": public_source_bank(source_bank),
        "message": (
            "Selected papers attached. Crossref-verified papers are citation-ready. "
            "Any paper without verified bibliographic metadata remains usable as uploaded evidence, but ProjectReady will not create a new citation from it until the user confirms its citation details."
        ),
    }


@router.patch("/{project_id}/selected-papers/{paper_id}")
def confirm_selected_paper_metadata(
    project_id: str,
    paper_id: str,
    payload: SelectedPaperMetadataUpdate,
) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    papers = profile.get("selected_papers") or []
    if not isinstance(papers, list):
        papers = []
    found = False
    updated_papers: list[dict[str, Any]] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        if str(paper.get("id") or "") == paper_id:
            paper = update_selected_paper_metadata(paper, payload.model_dump())
            found = True
        updated_papers.append(paper)
    if not found:
        raise HTTPException(status_code=404, detail="Selected paper not found.")
    profile["selected_papers"] = updated_papers[:MAX_SELECTED_PAPERS]
    source_bank = sync_selected_papers_to_source_bank(profile)
    _save_profile(project_id, profile)
    papers_public = _selected_paper_summaries(profile)
    updated = next(item for item in papers_public if str(item.get("id") or "") == paper_id)
    return {
        "project_id": project_id,
        "paper": updated,
        "papers": papers_public,
        "source_bank": public_source_bank(source_bank),
        "citation_ready": sum(1 for item in papers_public if item.get("citation_eligible")),
        "needs_metadata_confirmation": sum(1 for item in papers_public if not item.get("citation_eligible")),
    }


@router.delete("/{project_id}/selected-papers/{paper_id}")
def delete_selected_paper(project_id: str, paper_id: str) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    papers = profile.get("selected_papers") or []
    if not isinstance(papers, list):
        papers = []
    kept = [item for item in papers if isinstance(item, dict) and str(item.get("id") or "") != paper_id]
    if len(kept) == len([item for item in papers if isinstance(item, dict)]):
        raise HTTPException(status_code=404, detail="Selected paper not found.")
    profile["selected_papers"] = kept
    source_bank = sync_selected_papers_to_source_bank(profile)
    _save_profile(project_id, profile)
    public = _selected_paper_summaries(profile)
    return {
        "project_id": project_id,
        "papers": public,
        "count": len(public),
        "maximum": MAX_SELECTED_PAPERS,
        "capacity_remaining": max(0, MAX_SELECTED_PAPERS - len(public)),
        "source_bank": public_source_bank(source_bank),
    }


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ----------------------------------------------------------------------
# Pre-output claim-support review
# ----------------------------------------------------------------------

def _claim_review_key(workflow: str, chapter_number: int) -> str:
    mode = "strengthener" if str(workflow or "").strip().lower().startswith("strength") else "draft"
    return f"{mode}:{int(chapter_number or 0)}"


def _claim_review_text(project: dict[str, Any], workflow: str, chapter_number: int) -> tuple[str, str]:
    mode = "strengthener" if str(workflow or "").strip().lower().startswith("strength") else "draft"
    chapter = str(int(chapter_number or 0))
    if mode == "strengthener":
        profile = project.get("profile") or {}
        store = profile.get("chapter_strengthener") or {}
        record = store.get(chapter) if isinstance(store, dict) else None
        if isinstance(record, dict):
            text = str(record.get("revised_chapter_text") or "").strip()
            original = str(record.get("original_chapter_text") or "").strip()
            if text:
                return text, original
    text = str((project.get("drafts") or {}).get(chapter) or "").strip()
    return text, ""


def _review_store(profile: dict[str, Any]) -> dict[str, Any]:
    store = profile.get("claim_support_reviews") or {}
    if not isinstance(store, dict):
        store = {}
    profile["claim_support_reviews"] = store
    return store


def _ignored_review_store(profile: dict[str, Any]) -> dict[str, list[str]]:
    store = profile.get("claim_support_ignored") or {}
    if not isinstance(store, dict):
        store = {}
    profile["claim_support_ignored"] = store
    return store


def _review_ignore_key(item: dict[str, Any]) -> str:
    if str(item.get("type") or "") == "paragraph_density":
        heading = re.sub(r"\s+", " ", str(item.get("heading") or "")).strip().lower()
        return f"paragraph:{heading}:{int(item.get('paragraph_index') or 0)}"
    return str(item.get("id") or "")


def _apply_ignored_review_state(review: dict[str, Any], ignored_keys: list[str]) -> dict[str, Any]:
    ignored = {str(x) for x in (ignored_keys or []) if str(x)}
    if not ignored:
        review["ignored_item_count"] = 0
        return review
    removed = 0
    claims = []
    for item in review.get("claims") or []:
        if isinstance(item, dict) and _review_ignore_key(item) in ignored:
            removed += 1
            continue
        claims.append(item)
    gaps = []
    for item in review.get("paragraph_density_gaps") or []:
        if isinstance(item, dict) and _review_ignore_key(item) in ignored:
            removed += 1
            continue
        gaps.append(item)
    review["claims"] = claims
    review["paragraph_density_gaps"] = gaps
    review["unsupported_claim_count"] = len(claims)
    review["under_supported_paragraph_count"] = len(gaps)
    review["ignored_item_count"] = len(ignored)
    review["ignored_items_matching_current_text"] = removed
    review["claim_review_required"] = bool(claims)
    review["citation_density_review_required"] = bool(gaps)
    review["status"] = "review_required" if claims or gaps else "ready"
    review["final_output_ready"] = not bool(claims or gaps)
    return review


def _store_review_text(project_id: str, project: dict[str, Any], profile: dict[str, Any], *, workflow: str, chapter_number: int, text: str) -> None:
    chapter = str(int(chapter_number or 0))
    if str(workflow or "").lower().startswith("strength"):
        strengthener = profile.get("chapter_strengthener") or {}
        record = strengthener.get(chapter) if isinstance(strengthener, dict) else None
        if isinstance(record, dict):
            record["revised_chapter_text"] = text
            strengthener[chapter] = record
            profile["chapter_strengthener"] = strengthener
        _save_profile(project_id, profile)
        return
    drafts = project.get("drafts") or {}
    drafts[chapter] = text
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET drafts_json = ?, profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(drafts), json.dumps(profile), project_id),
        )
        conn.commit()


def _find_review_item(review: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for field in ("claims", "paragraph_density_gaps"):
        for item in review.get(field) or []:
            if isinstance(item, dict) and str(item.get("id") or "") == str(item_id or ""):
                return item
    return None


def _claim_search_tokens(value: str) -> set[str]:
    stop = {"the","and","for","with","that","this","from","into","among","their","have","has","been","were","was","are","can","may","study","research","evidence","results","findings"}
    return {token for token in re.findall(r"[a-z0-9]{3,}", str(value or "").lower()) if token not in stop}


def _project_evidence_candidates(profile: dict[str, Any], query: str, limit: int = 10) -> list[dict[str, Any]]:
    query_tokens = _claim_search_tokens(query)
    if not query_tokens:
        return []
    candidates: list[tuple[float, dict[str, Any]]] = []
    for source in profile.get("source_bank") or []:
        if not isinstance(source, dict):
            continue
        public = public_candidate(source)
        if not public.get("citation_eligible"):
            continue
        title_tokens = _claim_search_tokens(str(source.get("title") or ""))
        evidence_tokens = _claim_search_tokens(str(source.get("evidence_excerpt") or source.get("abstract") or ""))
        title_hits = len(query_tokens & title_tokens)
        evidence_hits = len(query_tokens & evidence_tokens)
        score = title_hits * 3 + evidence_hits
        if score < 2:
            continue
        copied = dict(source)
        databases = list(copied.get("databases_found") or [])
        if "Project evidence bank" not in databases:
            databases.append("Project evidence bank")
        copied["databases_found"] = databases
        copied["database"] = copied.get("database") or "Project evidence bank"
        copied["relevance_reason"] = copied.get("relevance_reason") or f"Matched {title_hits} title term(s) and {evidence_hits} accessible-evidence term(s) from this claim."
        copied["relevance_tier"] = copied.get("relevance_tier") or ("highly_relevant" if title_hits >= 2 or evidence_hits >= 4 else "partly_relevant")
        candidates.append((float(score), copied))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in candidates[:limit]]


def _candidate_record(item: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    for source in item.get("candidate_records") or []:
        if not isinstance(source, dict):
            continue
        public = public_candidate(source)
        if public.get("candidate_id") == candidate_id:
            return source
    return None


def _merge_review_state(new_review: dict[str, Any], old_review: dict[str, Any]) -> dict[str, Any]:
    old_by_id: dict[str, dict[str, Any]] = {}
    for field in ("claims", "paragraph_density_gaps"):
        for item in old_review.get(field) or []:
            if isinstance(item, dict) and item.get("id"):
                old_by_id[str(item["id"])] = item
    for field in ("claims", "paragraph_density_gaps"):
        for item in new_review.get(field) or []:
            previous = old_by_id.get(str(item.get("id") or ""))
            if not previous:
                continue
            for key in ("candidates", "candidate_records", "approved_sources", "last_search_query"):
                if previous.get(key):
                    item[key] = previous.get(key)
    return new_review


@router.get("/{project_id}/claim-support-review")
def get_claim_support_review(project_id: str, workflow: str = "draft", chapter_number: int = 1) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    text, original = _claim_review_text(project, workflow, chapter_number)
    if not text:
        raise HTTPException(status_code=404, detail="No chapter output is available for claim-support review.")
    key = _claim_review_key(workflow, chapter_number)
    store = _review_store(profile)
    old = store.get(key) if isinstance(store.get(key), dict) else {}
    review = _merge_review_state(
        build_claim_support_review(
            text,
            profile,
            chapter_number=chapter_number,
            workflow=workflow,
            original_text=original,
        ),
        old,
    )
    ignored_keys = (_ignored_review_store(profile).get(key) or [])
    review = _apply_ignored_review_state(review, ignored_keys)
    store[key] = review
    _save_profile(project_id, profile)
    return {"project_id": project_id, "review": review}


@router.post("/{project_id}/claim-support/find-sources")
def find_claim_support_sources(project_id: str, payload: ClaimSourceSearchRequest) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    text, original = _claim_review_text(project, payload.workflow, payload.chapter_number)
    if not text:
        raise HTTPException(status_code=404, detail="No chapter output is available for claim-support review.")
    key = _claim_review_key(payload.workflow, payload.chapter_number)
    store = _review_store(profile)
    review = store.get(key)
    if not isinstance(review, dict):
        review = build_claim_support_review(
            text, profile, chapter_number=payload.chapter_number, workflow=payload.workflow, original_text=original
        )
    item = _find_review_item(review, payload.claim_id)
    if not item:
        raise HTTPException(status_code=404, detail="The claim or paragraph evidence gap is no longer present in the current chapter.")
    query = str(payload.query or item.get("search_query") or item.get("claim_text") or item.get("paragraph_text") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="No searchable claim text is available.")
    try:
        result = search_literature_sources(
            profile=profile,
            query=query[:500],
            max_results=max(3, min(int(payload.max_results or 12), 20)),
            include_older_foundational=True,
            use_relevance_gate=True,
            attach_not_relevant_sources=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Claim source search failed: {str(exc)[:220]}") from exc

    external_records = [source for source in result.get("sources") or [] if isinstance(source, dict)]
    project_records = _project_evidence_candidates(profile, query, limit=10)
    records = _merge_sources(project_records, external_records, limit=24)
    item["candidate_records"] = records
    item["candidates"] = [public_candidate(source) for source in records]
    item["last_search_query"] = query
    store[key] = review
    _save_profile(project_id, profile)
    return {
        "project_id": project_id,
        "claim_id": payload.claim_id,
        "query": query,
        "candidates": item["candidates"],
        "provider_errors": result.get("provider_errors") or [],
        "provider_timings_ms": result.get("provider_timings_ms") or {},
        "databases": (["Project evidence bank"] if project_records else []) + list(result.get("databases") or []),
        "project_evidence_candidates": len(project_records),
        "external_searches": result.get("external_searches") or [],
        "usage_note": "Review the source evidence and approve only sources that actually support the highlighted claim. Search results are not inserted automatically. Google Scholar is offered as a manual external search because ProjectReady does not scrape it.",
    }


@router.post("/{project_id}/claim-support/approve")
def approve_claim_support_source(project_id: str, payload: ClaimSourceApprovalRequest) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    key = _claim_review_key(payload.workflow, payload.chapter_number)
    store = _review_store(profile)
    review = store.get(key)
    if not isinstance(review, dict):
        raise HTTPException(status_code=404, detail="Run the claim-support review and source search first.")
    item = _find_review_item(review, payload.claim_id)
    if not item:
        raise HTTPException(status_code=404, detail="Claim-support item not found.")
    source = _candidate_record(item, payload.candidate_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source candidate not found. Search again for this claim.")
    public = public_candidate(source)
    if not public.get("metadata_verified") or not public.get("citation_eligible"):
        raise HTTPException(status_code=422, detail="This source does not have verified bibliographic metadata and cannot be approved for citation.")
    if not payload.confirm_claim_support:
        raise HTTPException(status_code=422, detail="Confirm that this source actually supports the highlighted claim before approving it.")
    if public.get("requires_manual_source_text_confirmation") and not payload.confirm_source_text_reviewed:
        raise HTTPException(
            status_code=422,
            detail="Only metadata is available for this source. Open and review the source text, then confirm that you checked it before approval.",
        )

    approved = dict(source)
    approved["candidate_id"] = payload.candidate_id
    approved["user_verified"] = True
    approved["user_approved_for_claim_support"] = True
    approved["approved_claim_id"] = payload.claim_id
    approved["claim_support_basis"] = (
        "accessible abstract/evidence reviewed and approved by user"
        if public.get("claim_support_eligible")
        else "source text manually reviewed and approved by user"
    )
    if payload.confirm_source_text_reviewed:
        approved["claim_support_eligible"] = True
    stored = merge_source_into_bank(profile, approved)
    approvals = item.get("approved_sources") or []
    if not isinstance(approvals, list):
        approvals = []
    existing_ids = {public_candidate(x).get("candidate_id") for x in approvals if isinstance(x, dict)}
    approved_id = public_candidate(stored).get("candidate_id")
    if approved_id and approved_id not in existing_ids:
        approvals.append(stored)
    item["approved_sources"] = approvals[:3]
    item["status"] = "source_approved"
    # Approval resolves the stale source-needed marker immediately. The actual
    # verified citation is inserted only during the final apply step.
    current_text, _original = _claim_review_text(project, payload.workflow, payload.chapter_number)
    cleaned_text, placeholder_removed = remove_review_item_placeholder(current_text, item)
    item["placeholder_removed"] = bool(placeholder_removed)
    store[key] = review
    if cleaned_text != current_text:
        _store_review_text(project_id, project, profile, workflow=payload.workflow, chapter_number=payload.chapter_number, text=cleaned_text)
    else:
        _save_profile(project_id, profile)
    return {
        "project_id": project_id,
        "claim_id": payload.claim_id,
        "approved_source": public_candidate(stored),
        "approved_count": len(item["approved_sources"]),
        "source_bank_count": len(profile.get("source_bank") or []),
        "placeholder_removed": bool(placeholder_removed),
        "text": cleaned_text,
        "message": "Verified source approved. Any matching source-needed placeholder has been removed. Approve additional relevant sources if needed, then finalise the approved citations.",
    }


@router.post("/{project_id}/claim-support/ignore")
def ignore_claim_support_item(project_id: str, payload: ClaimSupportIgnoreRequest) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    key = _claim_review_key(payload.workflow, payload.chapter_number)
    store = _review_store(profile)
    review = store.get(key)
    if not isinstance(review, dict):
        raise HTTPException(status_code=404, detail="Run the claim-support review first.")
    item = _find_review_item(review, payload.claim_id)
    if not item:
        raise HTTPException(status_code=404, detail="This claim or paragraph evidence gap is no longer present.")

    current_text, original = _claim_review_text(project, payload.workflow, payload.chapter_number)
    cleaned_text, placeholder_removed = remove_review_item_placeholder(current_text, item)
    ignore_key = _review_ignore_key(item)
    ignored_store = _ignored_review_store(profile)
    ignored = list(ignored_store.get(key) or [])
    if ignore_key and ignore_key not in ignored:
        ignored.append(ignore_key)
    ignored_store[key] = ignored[-300:]
    item["status"] = "ignored"
    item["placeholder_removed"] = bool(placeholder_removed)

    refreshed = _merge_review_state(
        build_claim_support_review(
            cleaned_text, profile, chapter_number=payload.chapter_number, workflow=payload.workflow, original_text=original
        ),
        review,
    )
    refreshed = _apply_ignored_review_state(refreshed, ignored_store.get(key) or [])
    store[key] = refreshed
    _store_review_text(project_id, project, profile, workflow=payload.workflow, chapter_number=payload.chapter_number, text=cleaned_text)
    return {
        "project_id": project_id,
        "claim_id": payload.claim_id,
        "ignored": True,
        "placeholder_removed": bool(placeholder_removed),
        "text": cleaned_text,
        "review": refreshed,
        "message": "Item ignored by the user. Any matching source-needed placeholder was removed and the item will not be re-listed unless the text changes materially.",
    }


@router.post("/{project_id}/claim-support/apply-approved")
def apply_claim_support_citations(project_id: str, payload: ClaimCitationApplyRequest) -> dict[str, Any]:
    project = _get_project_or_404(project_id)
    profile = project.get("profile") or {}
    text, original = _claim_review_text(project, payload.workflow, payload.chapter_number)
    if not text:
        raise HTTPException(status_code=404, detail="No chapter output is available for claim-support review.")
    key = _claim_review_key(payload.workflow, payload.chapter_number)
    store = _review_store(profile)
    review = store.get(key)
    if not isinstance(review, dict):
        raise HTTPException(status_code=404, detail="Run the claim-support review first.")

    updated, apply_summary = apply_approved_claim_citations(
        text,
        review,
        citation_style=payload.citation_style or str(profile.get("citation_style") or "APA 7th"),
    )
    # The approved sources are now in the structured source bank, so the ordinary
    # citation-integrity gate can validate and rebuild the reference list safely.
    updated, integrity = remove_unverified_generated_citations(updated, profile, original_text=original or text)
    refreshed = build_claim_support_review(
        updated,
        profile,
        chapter_number=payload.chapter_number,
        workflow=payload.workflow,
        original_text=original,
    )
    refreshed = _merge_review_state(refreshed, review)
    ignored_keys = (_ignored_review_store(profile).get(key) or [])
    refreshed = _apply_ignored_review_state(refreshed, ignored_keys)
    refreshed["application_summary"] = apply_summary
    refreshed["citation_integrity"] = integrity
    refreshed["final_output_ready"] = not bool(
        refreshed.get("unsupported_claim_count") or refreshed.get("under_supported_paragraph_count")
    )
    refreshed["final_approval_summary"] = {
        "verified_citation_references_added": int(apply_summary.get("verified_citation_references_added") or 0),
        "citation_groups_added": int(apply_summary.get("citation_groups_added") or 0),
        "unique_verified_sources_added": int(apply_summary.get("unique_verified_sources_added") or 0),
        "ignored_items": int(refreshed.get("ignored_item_count") or 0),
        "remaining_claims_without_citations": int(refreshed.get("unsupported_claim_count") or 0),
        "remaining_paragraph_density_gaps": int(refreshed.get("under_supported_paragraph_count") or 0),
        "paragraph_minimum_coverage_percent": float((refreshed.get("paragraph_citation_audit") or {}).get("minimum_coverage_percent") or 0),
        "final_output_ready": bool(refreshed.get("final_output_ready")),
    }
    store[key] = refreshed

    chapter = str(int(payload.chapter_number or 0))
    if str(payload.workflow or "").lower().startswith("strength"):
        strengthener = profile.get("chapter_strengthener") or {}
        record = strengthener.get(chapter) if isinstance(strengthener, dict) else None
        if isinstance(record, dict):
            record["revised_chapter_text"] = updated
            record["claim_support_review"] = refreshed
            strengthener[chapter] = record
            profile["chapter_strengthener"] = strengthener
    else:
        drafts = project.get("drafts") or {}
        drafts[chapter] = updated
        with get_conn() as conn:
            conn.execute(
                "UPDATE projects SET drafts_json = ?, profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(drafts), json.dumps(profile), project_id),
            )
            conn.commit()
        save_draft_version(
            project_id,
            int(payload.chapter_number or 0),
            updated,
            source="claim_support_review",
            label="Claim-support citation review",
        )
        return {
            "project_id": project_id,
            "workflow": "draft",
            "chapter_number": payload.chapter_number,
            "text": updated,
            "review": refreshed,
            "application_summary": apply_summary,
            "citation_integrity": integrity,
        }

    _save_profile(project_id, profile)
    return {
        "project_id": project_id,
        "workflow": "strengthener",
        "chapter_number": payload.chapter_number,
        "text": updated,
        "review": refreshed,
        "application_summary": apply_summary,
        "citation_integrity": integrity,
    }
