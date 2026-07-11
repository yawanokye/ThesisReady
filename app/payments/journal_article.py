from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.journal_article_service import draft_journal_article, export_article_docx

router = APIRouter(prefix="/api/journal-article", tags=["journal article"])


class JournalArticleRequest(BaseModel):
    article_title: str = Field(..., min_length=3)
    research_area: str = ""
    target_journal: str = ""
    author_guidelines: str = ""
    article_type: str = "Empirical research article"
    academic_level: str = "Research Masters (e.g. MPhil)"
    methodology: str = ""
    context: str = ""
    research_problem: str = ""
    objectives: str = ""
    theory_or_framework: str = ""
    variables_constructs: str = ""
    data_and_results: str = ""
    key_findings: str = ""
    contribution: str = ""
    references_notes: str = ""
    word_limit: str = "6000-8000"
    citation_style: str = "APA 7th"
    include_source_search: bool = True
    include_older_foundational: bool = True


class ArticleExportRequest(BaseModel):
    article_title: str = "Journal Article Draft"
    article_text: str = Field(..., min_length=10)


@router.post("/draft")
def create_journal_article(payload: JournalArticleRequest) -> dict[str, Any]:
    try:
        return draft_journal_article(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Journal article drafting failed: {str(exc)[:240]}") from exc


@router.post("/export")
def export_journal_article(payload: ArticleExportRequest) -> StreamingResponse:
    try:
        stream, filename = export_article_docx(payload.article_text, payload.article_title)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Article export failed: {str(exc)[:240]}") from exc
