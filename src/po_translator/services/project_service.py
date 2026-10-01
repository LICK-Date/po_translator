"""Application service for Project lifecycle, persistence, and checkpoint resumption."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus
from po_translator.domain.models import PODocument
from po_translator.llm.models import LLMClient
from po_translator.po.reader import POReader
from po_translator.po.writer import POWriter
from po_translator.services.translation_service import (
    TranslationService,
    TranslationSummary,
)
from po_translator.storage.database import DatabaseManager
from po_translator.storage.repositories import (
    EntryRepository,
    ProjectRecord,
    ProjectRepository,
)
from po_translator.storage.translation_memory import TranslationMemory
from po_translator.translation.pipeline import TranslationConfig

logger = logging.getLogger(__name__)


class ProjectService:
    """Orchestrates persistent project management, checkpointing, and resumption after failure."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.entry_repo = EntryRepository(db)
        self.translation_memory = TranslationMemory(db)

    def create_project(
        self,
        name: str,
        po_path: Path | str,
        source_lang: str,
        target_lang: str,
        mode: str = "smart",
    ) -> tuple[ProjectRecord, PODocument]:
        """Create a new project from a PO file, persisting project and entries into database."""
        path_obj = Path(po_path).resolve()
        doc = POReader.read_file(path_obj)

        proj_id = hashlib.sha256(f"{name}:{path_obj}".encode()).hexdigest()[:12]
        project = ProjectRecord(
            id=proj_id,
            name=name,
            source_file=str(path_obj),
            source_language=source_lang,
            target_language=target_lang,
            mode=mode,
        )

        self.project_repo.save_project(project)
        self.entry_repo.save_entries(proj_id, doc.entries)
        logger.info("Project '%s' created with %d entries.", name, len(doc.entries))
        return project, doc

    async def run_or_resume_project(
        self,
        project_id: str,
        client: LLMClient,
        output_file: Path | str | None = None,
        overwrite: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[Path, TranslationSummary]:
        """Execute or resume project translation from checkpoint.

        Only entries in PENDING or FAILED status are sent for translation;
        completed (TRANSLATED or CACHED) entries are skipped completely.
        """
        project = self.project_repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        # Reload complete PO document
        doc = POReader.read_file(project.source_file)

        # Synchronize in-memory entries with database states
        db_entries = self.entry_repo.get_entries_by_status(
            project_id,
            [
                TranslationStatus.PENDING,
                TranslationStatus.TRANSLATED,
                TranslationStatus.CACHED,
                TranslationStatus.FAILED,
                TranslationStatus.REVIEW_REQUIRED,
            ],
        )
        status_map = {row["id"]: (row["status"], row["current_translation"]) for row in db_entries}

        for entry in doc.entries:
            if entry.id in status_map:
                st_val, trans = status_map[entry.id]
                entry.status = TranslationStatus(st_val)
                if trans:
                    entry.msgstr = trans

        # Configure translation service wired to database checkpointing and TM
        trans_service = TranslationService(
            client=client,
            translation_memory=self.translation_memory,
            entry_repo=self.entry_repo,
            project_id=project_id,
        )

        config = TranslationConfig(
            source_lang=project.source_language,
            target_lang=project.target_language,
        )

        # Execute translation on eligible entries (which skips TRANSLATED and CACHED)
        summary = await trans_service.translate_document(
            document=doc,
            config=config,
            filter_mode=FilterMode.UNTRANSLATED_ONLY,
            fuzzy_handling=FuzzyHandling.SKIP,
            progress_callback=progress_callback,
        )

        # Safely write updated document to target path
        in_path = Path(project.source_file)
        target_path = Path(output_file) if output_file else in_path.with_name(f"{in_path.stem}.translated{in_path.suffix}")
        saved_path = POWriter.write_file(doc, target_path, overwrite=overwrite)

        return saved_path, summary
