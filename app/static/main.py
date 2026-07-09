from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.payments.store import init_payment_tables
from app.routers import chapter_strengthener, generation, journal_article, payments, projects, sources, templates, topic_ideas

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ProjectReady AI",
    description="Guided academic research-development, chapter-strengthening and compliance workspace.",
    version="0.1.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(projects.router)
app.include_router(sources.router)
app.include_router(topic_ideas.router)
app.include_router(journal_article.router)
app.include_router(chapter_strengthener.router)
app.include_router(generation.router)
app.include_router(payments.api_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    init_payment_tables()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace() -> FileResponse:
    return FileResponse(STATIC_DIR / "workspace.html")


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
    return FileResponse(STATIC_DIR / "chapter_strengthener.html")


@app.get("/strengthen-chapter")
def strengthen_chapter_alias() -> FileResponse:
    return FileResponse(STATIC_DIR / "chapter_strengthener.html")

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
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/payment/recover")
def payment_recover_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "payment_recover.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
