from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import generation, journal_article, projects, sources, templates, topic_ideas

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ProjectReady AI",
    description="Customisable project work drafting and guideline-compliance assistant.",
    version="0.1.0",
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
app.include_router(generation.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace() -> FileResponse:
    return FileResponse(STATIC_DIR / "workspace.html")


@app.get("/topic-ideas")
def topic_ideas_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "topic_ideas.html")


@app.get("/ideas")
def ideas_page_alias() -> FileResponse:
    return FileResponse(STATIC_DIR / "topic_ideas.html")


@app.get("/journal-article")
def journal_article_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "journal_article.html")


@app.get("/article")
def article_page_alias() -> FileResponse:
    return FileResponse(STATIC_DIR / "journal_article.html")

@app.get("/register")
def register_redirect() -> FileResponse:
    # Registration is not yet implemented in the MVP. Send users to the workspace for now.
    return FileResponse(STATIC_DIR / "workspace.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
