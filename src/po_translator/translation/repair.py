"""Targeted repair mechanism for translations with placeholder or format issues."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from po_translator.exceptions import POTranslatorError
from po_translator.llm.models import LLMClient, LLMRequest, Message
from po_translator.po.placeholder import extract_placeholders
from po_translator.translation.prompts import build_repair_system_prompt
from po_translator.translation.validator import (
    ValidationContext,
    ValidationIssue,
    Validator,
)

logger = logging.getLogger(__name__)


class TranslationRepairer:
    """Attempts focused repairs on failed translations using targeted prompts and deterministic re-validation."""

    def __init__(self, client: LLMClient, validator: Validator) -> None:
        self.client = client
        self.validator = validator

    async def attempt_repair(
        self,
        source: str,
        incorrect_translation: str,
        errors: Sequence[ValidationIssue],
        context: ValidationContext | None = None,
        max_attempts: int = 2,
    ) -> tuple[bool, str, list[ValidationIssue]]:
        """Attempt to repair an invalid translation.

        Returns (success_boolean, final_translation, remaining_errors).
        """
        current_trans = incorrect_translation
        current_errors = list(errors)

        # Extract required placeholders to provide explicit hints in repair prompt
        required_phs = [p.raw for p in extract_placeholders(source, context.custom_patterns if context else None)]
        issue_descriptions = [err.message for err in errors]

        for attempt in range(max_attempts):
            logger.info("Attempting repair for text (attempt %d/%d)", attempt + 1, max_attempts)

            system_prompt = build_repair_system_prompt(
                source_text=source,
                incorrect_translation=current_trans,
                required_placeholders=required_phs,
                detected_issues=issue_descriptions,
            )

            req = LLMRequest(
                system_prompt=system_prompt,
                messages=[Message(role="user", content="Fix the translation according to instructions.")],
                temperature=0.0,
                response_schema={"type": "object"},
            )

            try:
                resp = await self.client.complete(req)
                clean_content = resp.content.strip()
                if clean_content.startswith("```"):
                    lines = clean_content.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_content = "\n".join(lines).strip()

                data = json.loads(clean_content)
                candidate_fixed = data.get("translation", "").strip()

                if not candidate_fixed:
                    continue

                # Re-validate repaired candidate
                val_res = self.validator.validate(source, candidate_fixed, context)
                if val_res.is_valid:
                    logger.info("Repair succeeded on attempt %d", attempt + 1)
                    return True, candidate_fixed, []

                current_trans = candidate_fixed
                current_errors = val_res.errors
                issue_descriptions = [err.message for err in val_res.errors]

            except (POTranslatorError, json.JSONDecodeError, OSError) as e:
                logger.warning("Repair call failed on attempt %d: %s", attempt + 1, e)

        return False, current_trans, current_errors
