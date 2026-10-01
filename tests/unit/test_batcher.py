"""Unit tests for TranslationBatcher and TranslationBatch."""

import json

import pytest

from po_translator.domain.models import TranslationEntry
from po_translator.exceptions import LLMResponseError
from po_translator.translation.batcher import TranslationBatch, TranslationBatcher


def make_entry(eid: str, msgid: str, msgid_plural: str | None = None) -> TranslationEntry:
    return TranslationEntry(
        id=eid,
        msgid=msgid,
        msgid_plural=msgid_plural,
    )


class TestTranslationBatcher:
    def test_split_by_entry_count(self):
        batcher = TranslationBatcher(max_entries_per_batch=3, max_chars_per_batch=1000)
        entries = [make_entry(f"id_{i}", f"Text {i}") for i in range(10)]

        batches = batcher.create_batches(entries)
        # 10 entries with max 3 per batch -> batches: 3, 3, 3, 1
        assert len(batches) == 4
        assert [b.size for b in batches] == [3, 3, 3, 1]

    def test_split_by_char_length(self):
        batcher = TranslationBatcher(max_entries_per_batch=10, max_chars_per_batch=500)
        long_text = "A" * 300
        entries = [make_entry(f"id_{i}", long_text) for i in range(4)]

        batches = batcher.create_batches(entries)
        # 4 entries of 300 chars: cannot fit 2 in 500 chars limit -> 4 batches of 1
        assert len(batches) == 4
        assert all(b.size == 1 for b in batches)

    def test_plural_entry_handling(self):
        batcher = TranslationBatcher(max_entries_per_batch=10, max_chars_per_batch=1000)
        plural_entry = make_entry("item_1", "You found a coin.", "You found %d coins.")
        batches = batcher.create_batches([plural_entry])

        assert len(batches) == 1
        batch = batches[0]
        assert batch.size == 2
        assert batch.items[0].target_key_id == "item_1"
        assert batch.items[1].target_key_id == "item_1:msgid_plural"

    def test_to_json_payload(self):
        batcher = TranslationBatcher(max_entries_per_batch=10)
        entries = [make_entry("e1", "Start"), make_entry("e2", "Exit")]
        batches = batcher.create_batches(entries)

        payload_str = batches[0].to_json_payload()
        payload = json.loads(payload_str)

        assert "entries" in payload
        assert len(payload["entries"]) == 2
        assert payload["entries"][0] == {"id": "e1", "text": "Start"}
        assert payload["entries"][1] == {"id": "e2", "text": "Exit"}


class TestBatchResponseParsing:
    def test_parse_valid_json(self):
        batch = TranslationBatch(batch_index=0)
        raw_json = json.dumps({
            "translations": [
                {"id": "e1", "translation": "开始"},
                {"id": "e2", "translation": "退出"},
            ]
        })
        result = batch.parse_response(raw_json)
        assert result == {"e1": "开始", "e2": "退出"}

    def test_parse_markdown_wrapped_json(self):
        batch = TranslationBatch(batch_index=0)
        wrapped = "```json\n" + json.dumps({
            "translations": [{"id": "e1", "translation": "开始"}]
        }) + "\n```"
        result = batch.parse_response(wrapped)
        assert result == {"e1": "开始"}

    def test_parse_invalid_json_fails(self):
        batch = TranslationBatch(batch_index=0)
        with pytest.raises(LLMResponseError, match="Failed to parse LLM response as JSON"):
            batch.parse_response("not valid json at all")

    def test_parse_missing_translations_key(self):
        batch = TranslationBatch(batch_index=0)
        with pytest.raises(LLMResponseError, match="must be an object with a 'translations' array"):
            batch.parse_response('{"data": []}')

    def test_parse_duplicate_id_fails(self):
        batch = TranslationBatch(batch_index=0)
        raw_json = json.dumps({
            "translations": [
                {"id": "e1", "translation": "开始"},
                {"id": "e1", "translation": "重新开始"},
            ]
        })
        with pytest.raises(LLMResponseError, match="Duplicate translation ID detected"):
            batch.parse_response(raw_json)
