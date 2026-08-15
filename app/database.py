from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def _is_postgres() -> bool:
    value = DATABASE_URL.lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def _sqlite_path_from_settings() -> Path:
    """Resolve SQLite storage from explicit path settings.

    Render users may set DATABASE_URL=/var/data/projectready.db. Older builds
    ignored that value unless it was PostgreSQL, which caused records to remain
    in the temporary application directory. This resolver accepts a plain file
    path or a sqlite:/// URL and still supports PROJECTREADY_SQLITE_DB_PATH.
    """
    explicit = os.getenv("PROJECTREADY_SQLITE_DB_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    value = DATABASE_URL.strip()
    if value and not _is_postgres():
        lowered = value.lower()
        if lowered.startswith("sqlite:////"):
            return Path("/" + value[len("sqlite:////"):]).expanduser()
        if lowered.startswith("sqlite:///"):
            return Path(value[len("sqlite:///"):]).expanduser()
        if "://" not in value:
            return Path(value).expanduser()

    return Path("projectready.db")


SQLITE_DB_PATH = _sqlite_path_from_settings()


class PostgresCompatConnection:
    """Small compatibility wrapper for the app's existing SQLite-style queries."""

    def __init__(self, connection: Any):
        self._connection = connection

    @staticmethod
    def _translate(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        cursor = self._connection.cursor()
        cursor.execute(self._translate(sql), tuple(params))
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def init_db() -> None:
    backend = "PostgreSQL" if _is_postgres() else f"SQLite at {SQLITE_DB_PATH}"
    print(f"ProjectReady database backend: {backend}")
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                selected_sections_json TEXT NOT NULL DEFAULT '{}',
                drafts_json TEXT NOT NULL DEFAULT '{}',
                checks_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_recovery (
                project_id TEXT PRIMARY KEY,
                recovery_email TEXT NOT NULL,
                recovery_pin_hash TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_recovery_email ON project_recovery(recovery_email)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_draft_versions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                draft_text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_draft_versions_project_chapter ON project_draft_versions(project_id, chapter_number, version_number)"
        )
        conn.commit()


@contextmanager
def get_conn() -> Iterator[Any]:
    if _is_postgres():
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("psycopg2-binary is required when DATABASE_URL uses PostgreSQL.") from exc

        raw = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn = PostgresCompatConnection(raw)
        try:
            yield conn
        finally:
            conn.close()
        return

    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ["profile_json", "selected_sections_json", "drafts_json", "checks_json"]:
        raw = data.pop(key, "{}")
        if isinstance(raw, (dict, list)):
            parsed = raw
        else:
            try:
                parsed = json.loads(raw or "{}")
            except Exception:
                parsed = {}
        data[key.replace("_json", "")] = parsed
    return data


def save_draft_version(
    project_id: str,
    chapter_number: int,
    draft_text: str,
    *,
    source: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Persist a recoverable chapter snapshot after each successful draft/revision."""
    import uuid

    text = str(draft_text or "")
    if not text.strip():
        raise ValueError("Cannot version an empty draft.")
    version_id = str(uuid.uuid4())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM project_draft_versions WHERE project_id = ? AND chapter_number = ?",
            (project_id, int(chapter_number)),
        ).fetchone()
        max_version = int((dict(row) if row is not None else {}).get("max_version") or 0)
        version_number = max_version + 1
        conn.execute(
            """
            INSERT INTO project_draft_versions
                (id, project_id, chapter_number, version_number, draft_text, source, label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, project_id, int(chapter_number), version_number, text, str(source or "")[:120], str(label or "")[:240]),
        )
        conn.commit()
    return {
        "id": version_id,
        "project_id": project_id,
        "chapter_number": int(chapter_number),
        "version_number": version_number,
        "source": str(source or "")[:120],
        "label": str(label or "")[:240],
        "character_count": len(text),
    }


def list_draft_versions(project_id: str, chapter_number: int, limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, chapter_number, version_number, source, label, created_at, LENGTH(draft_text) AS character_count
            FROM project_draft_versions
            WHERE project_id = ? AND chapter_number = ?
            ORDER BY version_number DESC
            LIMIT ?
            """,
            (project_id, int(chapter_number), max(1, min(int(limit or 20), 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_draft_version(project_id: str, chapter_number: int, version_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM project_draft_versions
            WHERE id = ? AND project_id = ? AND chapter_number = ?
            """,
            (version_id, project_id, int(chapter_number)),
        ).fetchone()
    return dict(row) if row is not None else None
