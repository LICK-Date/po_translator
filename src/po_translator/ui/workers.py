"""Background QThread workers ensuring non-blocking async execution for GUI."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PySide6.QtCore import QThread, Signal

from po_translator.domain.enums import FilterMode, FuzzyHandling
from po_translator.domain.models import PODocument
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.models import LLMClient
from po_translator.services.glossary_service import GlossaryService
from po_translator.services.translation_service import TranslationService
from po_translator.terminology.models import Glossary
from po_translator.translation.pipeline import TranslationConfig

logger = logging.getLogger(__name__)


class TranslationWorker(QThread):
    """Background worker for executing document translation via asyncio without freezing the UI."""

    progress_signal = Signal(int, int)
    finished_signal = Signal(object)  # TranslationSummary
    error_signal = Signal(str)
    cancelled_signal = Signal()

    def __init__(
        self,
        service: TranslationService,
        document: PODocument,
        config: TranslationConfig,
        filter_mode: FilterMode = FilterMode.UNTRANSLATED_ONLY,
        fuzzy_handling: FuzzyHandling = FuzzyHandling.SKIP,
    ) -> None:
        super().__init__()
        self.service = service
        self.document = document
        self.config = config
        self.filter_mode = filter_mode
        self.fuzzy_handling = fuzzy_handling
        self._is_cancelled = False

    def cancel(self) -> None:
        """Signal cancellation cleanly without killing the thread abruptly."""
        self._is_cancelled = True

    def run(self) -> None:
        """Execute the async translation loop within a dedicated event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def on_progress(completed: int, total: int) -> None:
            if not self._is_cancelled:
                self.progress_signal.emit(completed, total)

        async def _execute() -> Any:
            return await self.service.translate_document(
                document=self.document,
                config=self.config,
                filter_mode=self.filter_mode,
                fuzzy_handling=self.fuzzy_handling,
                progress_callback=on_progress,
            )

        try:
            summary = loop.run_until_complete(_execute())
            if self._is_cancelled:
                self.cancelled_signal.emit()
            else:
                self.finished_signal.emit(summary)
        except Exception as e:
            logger.exception("Translation worker encountered an error")
            self.error_signal.emit(f"Translation Error: {type(e).__name__} - {e}")
        finally:
            loop.close()


class ConnectionTestWorker(QThread):
    """Worker for asynchronously testing API connectivity."""

    result_signal = Signal(bool, str)

    def __init__(self, client: OpenAICompatibleClient) -> None:
        super().__init__()
        self.client = client

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ok, msg = loop.run_until_complete(self.client.test_connection())
            self.result_signal.emit(ok, msg)
        except Exception as e:
            logger.exception("Connection test failed")
            self.result_signal.emit(False, f"Connection Failed: {type(e).__name__} - {e}")
        finally:
            loop.close()


class GlossaryDiscoveryWorker(QThread):
    """Worker for executing automated terminology mining and translation."""

    finished_signal = Signal(object)  # Glossary
    error_signal = Signal(str)

    def __init__(
        self,
        service: GlossaryService,
        document: PODocument,
        source_lang: str,
        target_lang: str,
        client: LLMClient,
        existing_glossary: Glossary | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.document = document
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.client = client
        self.existing_glossary = existing_glossary

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            glossary = loop.run_until_complete(
                self.service.auto_build_glossary(
                    document=self.document,
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                    client=self.client,
                    existing_glossary=self.existing_glossary,
                )
            )
            self.finished_signal.emit(glossary)
        except Exception as e:
            logger.exception("Glossary discovery error")
            self.error_signal.emit(f"Terminology Error: {type(e).__name__} - {e}")
        finally:
            loop.close()
