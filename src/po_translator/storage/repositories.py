"""Database repositories for Projects and Translation Entries."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry
from po_translator.storage.database import DatabaseManager


@dataclass
class ProjectRecord:
    """Persistent project entity."""
    id: str
    name: str
    source_file: str
    source_language: str
    target_language: str
    mode: str = "smart"


class ProjectRepository:
    """Manages persistence for translation projects."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def save_project(self, project: ProjectRecord) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, source_file, source_language, target_language, mode)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    source_language = excluded.source_language,
                    target_language = excluded.target_language,
                    mode = excluded.mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project.id, project.name, project.source_file, project.source_language, project.target_language, project.mode),
            )

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT id, name, source_file, source_language, target_language, mode FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if row:
                return ProjectRecord(
                    id=row["id"],
                    name=row["name"],
                    source_file=row["source_file"],
                    source_language=row["source_language"],
                    target_language=row["target_language"],
                    mode=row["mode"],
                )
        return None


class EntryRepository:
    """Manages persistence and checkpoint states for translation entries."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def save_entries(self, project_id: str, entries: Sequence[TranslationEntry]) -> None:
        """Insert or sync translation entries for a project."""
        with self.db.transaction() as conn:
            params = []
            for e in entries:
                src_hash = hashlib.sha256(e.msgid.encode("utf-8")).hexdigest()[:16]
                params.append((
                    e.id,
                    project_id,
                    e.msgid,
                    e.msgctxt,
                    e.msgid_plural,
                    e.status.value,
                    e.msgstr,
                    src_hash,
                ))

            conn.executemany(
                """
                INSERT INTO entries (id, project_id, msgid, msgctxt, msgid_plural, status, current_translation, source_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, project_id) DO UPDATE SET
                    status = excluded.status,
                    current_translation = excluded.current_translation,
                    updated_at = CURRENT_TIMESTAMP
                """,
                params,
            )

    def checkpoint_batch_results(
        self,
        project_id: str,
        updates: Sequence[tuple[str, TranslationStatus, str | None]],
    ) -> None:
        """Atomically persist updates for a completed batch to support resume after crash."""
        with self.db.transaction() as conn:
            params = [
                (status.value, translation, project_id, entry_id)
                for entry_id, status, translation in updates
            ]
            conn.executemany(
                """
                UPDATE entries
                SET status = ?, current_translation = COALESCE(?, current_translation), updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND id = ?
                """,
                params,
            )

    def get_entries_by_status(
        self,
        project_id: str,
        statuses: Sequence[TranslationStatus],
    ) -> list[dict[str, str | None]]:
        """Retrieve entry records matching specified statuses."""
        with self.db.transaction() as conn:
            placeholders = ",".join("?" for _ in statuses)
            cursor = conn.execute(
                f"""
                SELECT id, msgid, msgctxt, msgid_plural, status, current_translation
                FROM entries
                WHERE project_id = ? AND status IN ({placeholders})
                """,
                [project_id, *(s.value for s in statuses)],
            )
            return [dict(row) for row in cursor.fetchall()]
