"""Translation pipeline coordinating batching, LLM execution, validation, and repair."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from po_translator.domain.enums import TranslationMode, TranslationStatus
from po_translator.domain.models import TranslationEntry
from po_translator.exceptions import POTranslatorError
from po_translator.llm.models import LLMClient, LLMRequest, Message
from po_translator.translation.batcher import BatchItem, TranslationBatch
from po_translator.translation.prompts import build_translate_system_prompt
from po_translator.translation.repair import TranslationRepairer
from po_translator.translation.validator import (
    CompositeValidator,
    ValidationContext,
    ValidationIssue,
    ValidationSeverity,
    Validator,
)

logger = logging.getLogger(__name__)


@dataclass
class TranslationConfig:
    """Settings controlling pipeline execution."""
    source_lang: str = "en"
    target_lang: str = "zh-CN"
    mode: TranslationMode = TranslationMode.SMART
    auto_repair: bool = True
    max_repairs: int = 2
    glossary_terms: list[tuple[str, str]] = field(default_factory=list)
    custom_patterns: list[str] = field(default_factory=list)


@dataclass
class ItemResult:
    """Result for a single batch item."""
    item: BatchItem
    status: TranslationStatus
    translation: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class BatchExecutionResult:
    """Outcome of processing an entire TranslationBatch."""
    batch_index: int
    item_results: list[ItemResult] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.item_results)

    @property
    def translated_count(self) -> int:
        return sum(1 for r in self.item_results if r.status == TranslationStatus.TRANSLATED)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.item_results if r.status == TranslationStatus.FAILED)

    @property
    def review_count(self) -> int:
        return sum(1 for r in self.item_results if r.status == TranslationStatus.REVIEW_REQUIRED)


class TranslationPipeline:
    """Executes a single or multi-stage translation workflow with validation and automated repair."""

    def __init__(
        self,
        client: LLMClient,
        validator: Validator | None = None,
        config: TranslationConfig | None = None,
    ) -> None:
        self.client = client
        self.validator = validator or CompositeValidator()
        self.config = config or TranslationConfig()
        self.repairer = TranslationRepairer(client=self.client, validator=self.validator)

    async def execute_batch(self, batch: TranslationBatch) -> BatchExecutionResult:
        """Process a single TranslationBatch through the pipeline."""
        system_prompt = build_translate_system_prompt(
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
            glossary_terms=self.config.glossary_terms,
        )

        user_content = batch.to_json_payload()
        request = LLMRequest(
            system_prompt=system_prompt,
            messages=[Message(role="user", content=user_content)],
            temperature=0.2,
            response_schema={"type": "object"},
        )

        try:
            response = await self.client.complete(request)
            raw_translations = batch.parse_response(response.content)
        except (POTranslatorError, json.JSONDecodeError, OSError) as exc:
            logger.error("Batch %d translation failed: %s", batch.batch_index, exc)
            # Mark all items in this batch as failed
            results = [
                ItemResult(
                    item=item,
                    status=TranslationStatus.FAILED,
                    issues=[ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category="llm_error",
                        message=f"LLM completion error: {exc}",
                    )],
                )
                for item in batch.items
            ]
            return BatchExecutionResult(batch_index=batch.batch_index, item_results=results)

        item_results: list[ItemResult] = []

        for item in batch.items:
            candidate_text = raw_translations.get(item.target_key_id)

            if candidate_text is None:
                item_results.append(
                    ItemResult(
                        item=item,
                        status=TranslationStatus.FAILED,
                        issues=[ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            category="missing_id",
                            message=f"Model response did not contain translation for item ID '{item.target_key_id}'.",
                        )],
                    )
                )
                continue

            ctx = ValidationContext(
                entry_id=item.entry_id,
                msgctxt=item.context,
                custom_patterns=self.config.custom_patterns,
                glossary_terms=self.config.glossary_terms,
            )

            # Step 1: Initial validation
            val_res = self.validator.validate(item.text, candidate_text, ctx)

            # Step 2: Auto-repair if errors exist and enabled
            final_text = candidate_text
            all_issues = list(val_res.errors) + list(val_res.warnings)

            if val_res.has_errors and self.config.auto_repair:
                repaired, fixed_text, remaining_errors = await self.repairer.attempt_repair(
                    source=item.text,
                    incorrect_translation=candidate_text,
                    errors=val_res.errors,
                    context=ctx,
                    max_attempts=self.config.max_repairs,
                )
                if repaired:
                    final_text = fixed_text
                    all_issues = list(val_res.warnings)  # Errors were cleared
                    val_res.is_valid = True
                else:
                    all_issues = list(remaining_errors) + list(val_res.warnings)

            # Step 3: Determine status
            if any(iss.severity.value == "error" for iss in all_issues):
                status = TranslationStatus.FAILED
                # Do NOT commit corrupted translation to final output
                final_text = None
            elif any(iss.severity.value == "warning" for iss in all_issues):
                status = TranslationStatus.REVIEW_REQUIRED
            else:
                status = TranslationStatus.TRANSLATED

            item_results.append(
                ItemResult(
                    item=item,
                    status=status,
                    translation=final_text,
                    issues=all_issues,
                )
            )

        return BatchExecutionResult(batch_index=batch.batch_index, item_results=item_results)

    def apply_batch_result_to_entries(
        self,
        batch_result: BatchExecutionResult,
        entry_map: dict[str, TranslationEntry],
    ) -> None:
        """Apply results back to domain TranslationEntry objects."""
        for res in batch_result.item_results:
            entry = entry_map.get(res.item.entry_id)
            if not entry:
                continue

            if res.item.target_key == "msgid":
                if res.translation is not None:
                    entry.msgstr = res.translation
                entry.status = res.status
            elif res.item.target_key == "msgid_plural":
                # For plural forms, update first plural index if translated
                if res.translation is not None:
                    entry.msgstr_plural[1] = res.translation
                if entry.status != TranslationStatus.FAILED:
                    entry.status = res.status
