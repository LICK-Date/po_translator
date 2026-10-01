"""Application service coordinating file translation workflows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus
from po_translator.domain.models import PODocument, TranslationEntry
from po_translator.llm.models import LLMClient
from po_translator.po.reader import POReader
from po_translator.po.writer import POWriter
from po_translator.translation.batcher import TranslationBatcher
from po_translator.translation.pipeline import (
    TranslationConfig,
    TranslationPipeline,
)

logger = logging.getLogger(__name__)


@dataclass
class TranslationSummary:
    """Summary metrics of an executed translation job."""
    total_entries: int
    translatable_entries: int
    translated_count: int
    cached_count: int
    failed_count: int
    review_count: int
    skipped_count: int


class TranslationService:
    """Unified service for translating PO files and documents.

    Both CLI and GUI call into this service to execute translation jobs.
    """

    def __init__(
        self,
        client: LLMClient,
        pipeline: TranslationPipeline | None = None,
        batcher: TranslationBatcher | None = None,
        translation_memory: Any | None = None,
        entry_repo: Any | None = None,
        project_id: str | None = None,
    ) -> None:
        self.client = client
        self.pipeline = pipeline or TranslationPipeline(client=self.client)
        self.batcher = batcher or TranslationBatcher()
        self.translation_memory = translation_memory
        self.entry_repo = entry_repo
        self.project_id = project_id

    async def translate_document(
        self,
        document: PODocument,
        config: TranslationConfig | None = None,
        filter_mode: FilterMode = FilterMode.UNTRANSLATED_ONLY,
        fuzzy_handling: FuzzyHandling = FuzzyHandling.SKIP,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> TranslationSummary:
        """Translate applicable entries in a PODocument in-place."""
        active_config = config or self.pipeline.config
        self.pipeline.config = active_config

        # 1. Select eligible entries
        eligible_entries = [
            e for e in document.entries
            if e.is_candidate_for_translation(filter_mode, fuzzy_handling)
        ]

        if not eligible_entries:
            return TranslationSummary(
                total_entries=len(document.entries),
                translatable_entries=0,
                translated_count=0,
                cached_count=0,
                failed_count=0,
                review_count=0,
                skipped_count=len(document.entries),
            )

        cached_cnt = 0
        entries_for_llm: list[TranslationEntry] = []

        # 2. Check Translation Memory (TM lookup)
        for entry in eligible_entries:
            if self.translation_memory and self.translation_memory.enabled and not entry.is_plural:
                cached_target = self.translation_memory.lookup(
                    source_lang=active_config.source_lang,
                    target_lang=active_config.target_lang,
                    msgid=entry.msgid,
                    msgctxt=entry.msgctxt,
                )
                if cached_target is not None:
                    entry.msgstr = cached_target
                    entry.status = TranslationStatus.CACHED
                    cached_cnt += 1
                    # Checkpoint immediately if repository configured
                    if self.entry_repo and self.project_id:
                        self.entry_repo.checkpoint_batch_results(
                            self.project_id,
                            [(entry.id, TranslationStatus.CACHED, cached_target)],
                        )
                    continue

            entries_for_llm.append(entry)

        entry_map = {e.id: e for e in entries_for_llm}

        # 3. Divide remaining entries into batches
        batches = self.batcher.create_batches(entries_for_llm)
        total_batches = len(batches)
        logger.info(
            "TM hit: %d. Created %d batches for %d entries requiring LLM.",
            cached_cnt,
            total_batches,
            len(entries_for_llm),
        )

        # 4. Process batches sequentially with immediate checkpointing
        for processed_batches, batch in enumerate(batches, start=1):
            batch_result = await self.pipeline.execute_batch(batch)
            self.pipeline.apply_batch_result_to_entries(batch_result, entry_map)

            # Store successful translations in Translation Memory
            if self.translation_memory and self.translation_memory.enabled:
                for res in batch_result.item_results:
                    if res.status == TranslationStatus.TRANSLATED and res.translation and res.item.target_key == "msgid":
                        self.translation_memory.store(
                            source_lang=active_config.source_lang,
                            target_lang=active_config.target_lang,
                            msgid=res.item.text,
                            target_text=res.translation,
                            msgctxt=res.item.context,
                        )

            # Atomic checkpoint to SQLite per completed batch
            if self.entry_repo and self.project_id:
                updates = [
                    (res.item.entry_id, res.status, res.translation)
                    for res in batch_result.item_results
                ]
                self.entry_repo.checkpoint_batch_results(self.project_id, updates)

            if progress_callback:
                progress_callback(processed_batches, total_batches)

        # 5. Compute summary
        translated_cnt = sum(1 for e in eligible_entries if e.status == TranslationStatus.TRANSLATED)
        failed_cnt = sum(1 for e in eligible_entries if e.status == TranslationStatus.FAILED)
        review_cnt = sum(1 for e in eligible_entries if e.status == TranslationStatus.REVIEW_REQUIRED)
        skipped_cnt = len(document.entries) - len(eligible_entries)

        return TranslationSummary(
            total_entries=len(document.entries),
            translatable_entries=len(eligible_entries),
            translated_count=translated_cnt,
            cached_count=cached_cnt,
            failed_count=failed_cnt,
            review_count=review_cnt,
            skipped_count=skipped_cnt,
        )

    async def translate_file(
        self,
        input_file: Path | str,
        output_file: Path | str | None = None,
        config: TranslationConfig | None = None,
        filter_mode: FilterMode = FilterMode.UNTRANSLATED_ONLY,
        fuzzy_handling: FuzzyHandling = FuzzyHandling.SKIP,
        overwrite: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[Path, TranslationSummary]:
        """Full end-to-end file translation: read -> translate -> write safely."""
        in_path = Path(input_file)
        if output_file is None:
            out_path = in_path.with_name(f"{in_path.stem}.translated{in_path.suffix}")
        else:
            out_path = Path(output_file)

        doc = POReader.read_file(in_path)
        summary = await self.translate_document(
            document=doc,
            config=config,
            filter_mode=filter_mode,
            fuzzy_handling=fuzzy_handling,
            progress_callback=progress_callback,
        )

        saved_path = POWriter.write_file(
            document=doc,
            target_path=out_path,
            overwrite=overwrite,
        )

        return saved_path, summary
