"""Unit tests for SQLite database management and repositories."""

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry
from po_translator.storage.database import DatabaseManager
from po_translator.storage.repositories import (
    EntryRepository,
    ProjectRecord,
    ProjectRepository,
)


class TestDatabaseAndRepositories:
    def test_database_initialization(self):
        db = DatabaseManager(":memory:")
        with db.transaction() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cursor.fetchall()]

        assert "projects" in tables
        assert "entries" in tables
        assert "translation_memory" in tables
        assert "translation_results" in tables

    def test_project_repository(self):
        db = DatabaseManager(":memory:")
        repo = ProjectRepository(db)

        proj = ProjectRecord(
            id="proj_1",
            name="Game Localization",
            source_file="/path/to/game.po",
            source_language="en",
            target_language="zh-CN",
        )
        repo.save_project(proj)

        fetched = repo.get_project("proj_1")
        assert fetched is not None
        assert fetched.name == "Game Localization"
        assert fetched.target_language == "zh-CN"

    def test_entry_repository_and_checkpoint(self):
        db = DatabaseManager(":memory:")
        proj_repo = ProjectRepository(db)
        entry_repo = EntryRepository(db)

        proj_repo.save_project(ProjectRecord(
            id="p1",
            name="P1",
            source_file="test.po",
            source_language="en",
            target_language="zh-CN",
        ))

        entries = [
            TranslationEntry(id="e1", msgid="Start", status=TranslationStatus.PENDING),
            TranslationEntry(id="e2", msgid="Exit", status=TranslationStatus.PENDING),
        ]
        entry_repo.save_entries("p1", entries)

        pending = entry_repo.get_entries_by_status("p1", [TranslationStatus.PENDING])
        assert len(pending) == 2

        # Checkpoint e1 as TRANSLATED
        entry_repo.checkpoint_batch_results(
            "p1",
            [("e1", TranslationStatus.TRANSLATED, "开始")],
        )

        translated = entry_repo.get_entries_by_status("p1", [TranslationStatus.TRANSLATED])
        assert len(translated) == 1
        assert translated[0]["id"] == "e1"
        assert translated[0]["current_translation"] == "开始"
