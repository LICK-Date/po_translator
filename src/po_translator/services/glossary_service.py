"""Application service managing terminology workflows and glossary lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from po_translator.domain.models import PODocument
from po_translator.llm.models import LLMClient
from po_translator.terminology.extractor import TermExtractor
from po_translator.terminology.llm_filter import LLMTermProcessor
from po_translator.terminology.matcher import GlossaryMatcher
from po_translator.terminology.models import (
    Glossary,
    GlossaryTerm,
    TermCandidate,
)

logger = logging.getLogger(__name__)


class GlossaryService:
    """Orchestrates candidate mining, LLM qualification, translation, and matching."""

    def __init__(
        self,
        extractor: TermExtractor | None = None,
        processor: type[LLMTermProcessor] | None = None,
        matcher: type[GlossaryMatcher] | None = None,
    ) -> None:
        self.extractor = extractor or TermExtractor()
        self.processor = processor or LLMTermProcessor
        self.matcher = matcher or GlossaryMatcher

    def discover_candidates(
        self,
        document: PODocument,
        lang: str = "en",
    ) -> list[TermCandidate]:
        """Extract candidate terminology algorithmically from a PO document."""
        return self.extractor.extract_from_entries(document.entries, lang=lang)

    async def auto_build_glossary(
        self,
        document: PODocument,
        source_lang: str,
        target_lang: str,
        client: LLMClient,
        existing_glossary: Glossary | None = None,
    ) -> Glossary:
        """Full end-to-end automatic glossary generation pipeline.

        1. Algorithmically mine candidates.
        2. Filter through LLM.
        3. Translate approved terms through LLM.
        4. Merge into glossary respecting locked terms and priority hierarchy.
        """
        glossary = existing_glossary or Glossary()

        # Step 1: Algorithmic extraction
        candidates = self.discover_candidates(document, lang=source_lang)
        if not candidates:
            return glossary

        # Step 2: Filter with LLM
        filtered_terms = await self.processor.filter_candidates(candidates, client=client)
        if not filtered_terms:
            return glossary

        # Step 3: Only translate terms that do not already have locked translations
        terms_to_translate: list[GlossaryTerm] = []
        for term in filtered_terms:
            existing = glossary.get(term.source)
            if existing and existing.locked and existing.target:
                continue
            terms_to_translate.append(term)

        translated_terms = await self.processor.translate_terms(
            terms_to_translate,
            source_lang=source_lang,
            target_lang=target_lang,
            client=client,
        )

        # Step 4: Add into glossary
        for t in translated_terms:
            glossary.add_term(t, overwrite_locked=False)

        return glossary

    def match_batch_terms(
        self,
        batch_texts: Sequence[str],
        glossary: Glossary,
    ) -> list[tuple[str, str]]:
        """Match terms present in the current batch and return (source, target) tuples."""
        matched_records = self.matcher.match_batch(batch_texts, glossary)
        # Return only terms that have a target translation
        return [(t.source, t.target) for t in matched_records if t.target]
