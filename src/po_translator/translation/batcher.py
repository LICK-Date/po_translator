"""Batch translation grouping and payload serialization."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from po_translator.domain.models import TranslationEntry
from po_translator.exceptions import LLMResponseError


@dataclass
class BatchItem:
    """A single translatable unit within a batch."""
    entry_id: str
    target_key: str  # "msgid" or "msgid_plural"
    text: str
    context: str | None = None


@dataclass
class TranslationBatch:
    """A collection of BatchItems grouped together for a single LLM request."""
    batch_index: int
    items: list[BatchItem] = field(default_factory=list)
    char_count: int = 0

    @property
    def size(self) -> int:
        return len(self.items)

    def to_json_payload(self) -> str:
        """Serialize batch items to the JSON structure required by prompt."""
        entries_payload = [
            {"id": item.target_key_id, "text": item.text}
            for item in self.items
        ]
        return json.dumps({"entries": entries_payload}, ensure_ascii=False, indent=2)

    def parse_response(self, response_content: str) -> dict[str, str]:
        """Parse and validate structured JSON returned from LLM.

        Returns mapping from target_key_id to translation string.
        Raises LLMResponseError on malformed JSON or invalid schema.
        """
        try:
            # Strip markdown code blocks if model wrapped it in ```json ... ```
            clean_content = response_content.strip()
            if clean_content.startswith("```"):
                lines = clean_content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_content = "\n".join(lines).strip()

            data = json.loads(clean_content)
        except json.JSONDecodeError as err:
            raise LLMResponseError(f"Failed to parse LLM response as JSON: {err}") from err

        if not isinstance(data, dict) or "translations" not in data:
            raise LLMResponseError("JSON response must be an object with a 'translations' array.")

        translations_list = data["translations"]
        if not isinstance(translations_list, list):
            raise LLMResponseError("'translations' field must be a JSON array.")

        result_map: dict[str, str] = {}
        for item in translations_list:
            if not isinstance(item, dict):
                raise LLMResponseError(f"Each translation item must be an object, got {type(item).__name__}")
            if "id" not in item or "translation" not in item:
                raise LLMResponseError("Translation item is missing required 'id' or 'translation' key.")

            item_id = str(item["id"])
            if item_id in result_map:
                raise LLMResponseError(f"Duplicate translation ID detected in response: '{item_id}'")

            result_map[item_id] = str(item["translation"])

        return result_map


# Property for BatchItem to create an unambiguous item ID
@property
def _target_key_id(self: BatchItem) -> str:
    if self.target_key == "msgid":
        return self.entry_id
    return f"{self.entry_id}:{self.target_key}"


BatchItem.target_key_id = _target_key_id  # type: ignore[attr-defined]


class TranslationBatcher:
    """Divides entries into bounded batches obeying entry-count and character-length limits."""

    def __init__(
        self,
        max_entries_per_batch: int = 30,
        max_chars_per_batch: int = 10000,
    ) -> None:
        self.max_entries_per_batch = max(1, max_entries_per_batch)
        self.max_chars_per_batch = max(500, max_chars_per_batch)

    def create_batches(self, entries: Sequence[TranslationEntry]) -> list[TranslationBatch]:
        """Split translation entries into appropriately sized batches."""
        batches: list[TranslationBatch] = []
        current_batch = TranslationBatch(batch_index=0)

        for entry in entries:
            # Generate items for this entry (singular and plural if present)
            items_to_add: list[BatchItem] = []
            if entry.msgid:
                items_to_add.append(
                    BatchItem(
                        entry_id=entry.id,
                        target_key="msgid",
                        text=entry.msgid,
                        context=entry.msgctxt,
                    )
                )
            if entry.msgid_plural:
                items_to_add.append(
                    BatchItem(
                        entry_id=entry.id,
                        target_key="msgid_plural",
                        text=entry.msgid_plural,
                        context=entry.msgctxt,
                    )
                )

            for item in items_to_add:
                item_len = len(item.text)

                # Check if adding this item violates batch constraints
                would_exceed_count = current_batch.size >= self.max_entries_per_batch
                would_exceed_chars = (
                    current_batch.char_count + item_len > self.max_chars_per_batch
                    and current_batch.size > 0
                )

                if would_exceed_count or would_exceed_chars:
                    batches.append(current_batch)
                    current_batch = TranslationBatch(batch_index=len(batches))

                current_batch.items.append(item)
                current_batch.char_count += item_len

        if current_batch.items:
            batches.append(current_batch)

        return batches
