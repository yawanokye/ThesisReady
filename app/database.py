from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_DB_PATH = Path(os.getenv("PROJECTREADY_SQLITE_DB_PATH", "projectready.db"))


def _is_postgres() -> bool:
    value = DATABASE_URL.lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


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
