from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from starlette.requests import Request

from app.routers.chapter_strengthener import strengthen_project_chapter
from app.routers.generation import draft_chapter
from app.schemas import ChapterRevisionRequest, DraftRequest


class PermanentJobError(RuntimeError):
    """A request problem that should not be retried by another worker attempt."""


def _worker_request(path: str, claim: dict[str, Any] | None = None) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("background-worker", 0),
        "server": ("background-worker", 443),
    }
    request = Request(scope)
    request.state.preauthorized_claim = claim or {}
    request.state.background_job = True
    return request


def process_job(job: dict[str, Any], progress: Callable[[int, str, str], None]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    job_type = str(job.get("job_type") or "")
    project_id = str(job.get("project_id") or payload.get("project_id") or "")
    claim = payload.get("_preauthorized_claim") or {}

    try:
        if job_type == "chapter_draft":
            progress(15, "preparing", "Preparing the chapter profile, sections and alignment context.")
            request_payload = DraftRequest(**(payload.get("request") or {}))
            progress(30, "generating", "Developing the chapter in the background. Long chapters may take several minutes.")
            result = draft_chapter(
                project_id,
                request_payload,
                _worker_request(f"/api/projects/{project_id}/draft", claim),
            )
            progress(90, "saving", "Saving the completed working draft and quality metrics.")
            return result

        if job_type == "chapter_strengthener":
            progress(15, "preparing", "Preparing the selected chapter and strengthening scope.")
            request_payload = ChapterRevisionRequest(**(payload.get("request") or {}))
            progress(30, "strengthening", "Strengthening the selected chapter or sections in the background.")
            result = strengthen_project_chapter(
                project_id,
                request_payload,
                _worker_request(f"/api/projects/{project_id}/chapter-strengthener/revise", claim),
            )
            progress(90, "saving", "Saving the strengthened chapter and revision report.")
            return result

        raise PermanentJobError(f"Unsupported background job type: {job_type}")
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or detail)
        else:
            message = str(detail)
        if int(exc.status_code or 500) < 500:
            raise PermanentJobError(message) from exc
        raise RuntimeError(message) from exc
    except (ValueError, TypeError) as exc:
        raise PermanentJobError(str(exc)) from exc
