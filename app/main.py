from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import generation, projects, sources, templates

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
app.include_router(generation.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
@app.get("/index.html")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
@app.get("/workspace/")
@app.get("/workspace.html")
def workspace() -> FileResponse:
    return FileResponse(STATIC_DIR / "workspace.html")


@app.get("/register")
def register_redirect() -> FileResponse:
    # Registration is not yet implemented in the MVP. Send users to the workspace for now.
    return FileResponse(STATIC_DIR / "workspace.html")


@app.get("/favicon.ico")
def favicon() -> Response:
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return Response(status_code=204)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
