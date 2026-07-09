from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Any

from app.database import get_conn, row_to_dict

PIN_PATTERN = re.compile(r"^\d{6}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PBKDF2_ITERATIONS = max(
    80_000,
    int(os.getenv("PROJECTREADY_RECOVERY_PBKDF2_ITERATIONS", "150000")),
)


def normalise_recovery_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("Enter a valid recovery email address.")
    return email


def validate_recovery_pin(value: str) -> str:
    pin = str(value or "").strip()
    if not PIN_PATTERN.fullmatch(pin):
        raise ValueError("Recovery PIN must contain exactly 6 digits.")
    return pin


def _hash_pin(pin: str) -> str:
    validated = validate_recovery_pin(pin)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        validated.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_pin(pin: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = str(encoded or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        supplied = hashlib.pbkdf2_hmac(
            "sha256",
            validate_recovery_pin(pin).encode("utf-8"),
            bytes.fromhex(salt_hex),
            iterations,
        ).hex()
        return hmac.compare_digest(supplied, digest_hex)
    except Exception:
        return False


def set_project_recovery(project_id: str, email: str, pin: str) -> dict[str, Any]:
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("Project ID is required.")
    email_value = normalise_recovery_email(email)
    pin_hash = _hash_pin(pin)

    with get_conn() as conn:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise ValueError("Project not found.")

        existing = conn.execute(
            "SELECT project_id FROM project_recovery WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE project_recovery
                SET recovery_email = ?, recovery_pin_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
                """,
                (email_value, pin_hash, project_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO project_recovery (
                    project_id, recovery_email, recovery_pin_hash, created_at, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (project_id, email_value, pin_hash),
            )
        conn.commit()

    return {
        "project_id": project_id,
        "recovery_email": email_value,
        "recovery_enabled": True,
    }


def recovery_enabled(project_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM project_recovery WHERE project_id = ?",
            (str(project_id or "").strip(),),
        ).fetchone()
    return bool(row)


def recover_projects(email: str, pin: str) -> list[dict[str, Any]]:
    email_value = normalise_recovery_email(email)
    pin_value = validate_recovery_pin(pin)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.*, r.recovery_pin_hash
            FROM project_recovery r
            JOIN projects p ON p.id = r.project_id
            WHERE r.recovery_email = ?
            ORDER BY p.updated_at DESC
            """,
            (email_value,),
        ).fetchall()

    recovered: list[dict[str, Any]] = []
    for row in rows:
        raw = dict(row)
        if not _verify_pin(pin_value, str(raw.pop("recovery_pin_hash", ""))):
            continue
        project = row_to_dict(raw) or {}
        profile = project.get("profile") or {}
        recovered.append(
            {
                "id": project.get("id"),
                "title": project.get("title"),
                "academic_level": profile.get("level", ""),
                "project_kind": profile.get("project_kind", "standard"),
                "chapter_type": profile.get("external_revision_chapter_type", ""),
                "created_at": str(project.get("created_at") or ""),
                "updated_at": str(project.get("updated_at") or ""),
            }
        )
    return recovered
