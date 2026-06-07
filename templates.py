from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.template_store import get_chapter, load_default_template

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("/default")
def get_default_template():
    return load_default_template()


@router.get("/default/chapters/{chapter_number}")
def get_template_chapter(chapter_number: int):
    try:
        return get_chapter(chapter_number)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
