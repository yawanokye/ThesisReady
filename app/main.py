from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.internal_portal import init_internal_portal_tables, internal_session_or_none, router as internal_portal_router
from app.jobs.store import init_job_tables
from app.payments.store import init_payment_tables
from app.routers import chapter_strengthener, generation, jobs, journal_article, payments, projects, sources, templates, topic_ideas

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _truthy(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _allowed_origins() -> list[str]:
    raw = str(os.getenv("PROJECTREADY_ALLOWED_ORIGINS") or "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    init_payment_tables()
    init_job_tables()
    init_internal_portal_tables()
    yield


expose_docs = _truthy("PROJECTREADY_EXPOSE_API_DOCS", "0")
app = FastAPI(
    title="ProjectReady AI",
    description="Guided academic research-development, chapter-strengthening and compliance workspace.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if expose_docs else None,
    redoc_url="/redoc" if expose_docs else None,
    openapi_url="/openapi.json" if expose_docs else None,
)


@app.middleware("http")
async def attach_internal_portal_session(request, call_next):
    """Validate the restricted portal cookie once for every same-origin request.

    Protected module routes can then recognise authorised developer access on
    the server without depending only on localStorage or custom browser headers.
    """
    request.state.internal_portal_session = internal_session_or_none(request)
    return await call_next(request)

origins = _allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=bool(origins),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Idempotency-Key",
        "X-ProjectReady-Purchase-Id",
        "X-ProjectReady-Access-Token",
        "X-ProjectReady-Job-Token",
    ],
)

app.include_router(templates.router)
app.include_router(projects.router)
app.include_router(sources.router)
app.include_router(topic_ideas.router)
app.include_router(journal_article.router)
app.include_router(chapter_strengthener.router)
app.include_router(generation.router)
app.include_router(jobs.router)
app.include_router(payments.api_router)
app.include_router(internal_portal_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "workspace.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/topic-ideas")
def topic_ideas_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "topic_ideas.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/ideas")
def ideas_page_alias() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "topic_ideas.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/journal-article")
def journal_article_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "journal_article.html")


@app.get("/article")
def article_page_alias() -> FileResponse:
    return FileResponse(STATIC_DIR / "journal_article.html")


@app.get("/chapter-strengthener")
def chapter_strengthener_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "chapter_strengthener.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/strengthen-chapter")
def strengthen_chapter_alias() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "chapter_strengthener.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/register")
def register_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "register.html")


@app.get("/academic-integrity")
def academic_integrity_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "academic_integrity.html")


@app.get("/terms")
def terms_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "terms.html")


@app.get("/admin/payment-recovery")
def payment_recovery_admin_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "payment_recovery_admin.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow"},
    )


@app.get("/payment/recover")
def payment_recover_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "payment_recover.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "background_jobs": "enabled" if _truthy("PROJECTREADY_BACKGROUND_JOBS_ENABLED", "1") else "disabled"}
