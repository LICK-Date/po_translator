"""Unit tests for TranslationPipeline and automated repair."""

import json

import pytest

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry
from po_translator.llm.fake_client import FakeLLMClient
from po_translator.translation.batcher import BatchItem, TranslationBatch
from po_translator.translation.pipeline import (
    TranslationConfig,
    TranslationPipeline,
)


@pytest.fixture
def fake_client():
    return FakeLLMClient()


class TestTranslationPipeline:
    @pytest.mark.asyncio
    async def test_normal_batch_translation(self, fake_client):
        # Configure fake client response
        batch_resp = json.dumps({
            "translations": [
                {"id": "entry1", "translation": "开始游戏"},
                {"id": "entry2", "translation": "退出游戏"},
            ]
        })
        fake_client.queue_response(batch_resp)

        pipeline = TranslationPipeline(client=fake_client)

        batch = TranslationBatch(
            batch_index=0,
            items=[
                BatchItem(entry_id="entry1", target_key="msgid", text="Start Game"),
                BatchItem(entry_id="entry2", target_key="msgid", text="Exit Game"),
            ],
        )

        res = await pipeline.execute_batch(batch)
        assert res.total_count == 2
        assert res.translated_count == 2
        assert res.failed_count == 0

        # Apply to domain models
        e1 = TranslationEntry(id="entry1", msgid="Start Game")
        e2 = TranslationEntry(id="entry2", msgid="Exit Game")
        entry_map = {"entry1": e1, "entry2": e2}

        pipeline.apply_batch_result_to_entries(res, entry_map)
        assert e1.msgstr == "开始游戏"
        assert e1.status == TranslationStatus.TRANSLATED
        assert e2.msgstr == "退出游戏"
        assert e2.status == TranslationStatus.TRANSLATED

    @pytest.mark.asyncio
    async def test_placeholder_repair_success(self, fake_client):
        # 1. Batch call returns broken placeholder ({username} -> {用户名})
        batch_resp = json.dumps({
            "translations": [
                {"id": "entry_ph", "translation": "欢迎，{用户名}！"},
            ]
        })
        fake_client.queue_response(batch_resp)

        # 2. Repair call returns properly repaired placeholder
        repair_resp = json.dumps({
            "translation": "欢迎，{username}！"
        })
        fake_client.queue_response(repair_resp)

        pipeline = TranslationPipeline(
            client=fake_client,
            config=TranslationConfig(auto_repair=True, max_repairs=2),
        )

        batch = TranslationBatch(
            batch_index=0,
            items=[
                BatchItem(entry_id="entry_ph", target_key="msgid", text="Welcome, {username}!"),
            ],
        )

        res = await pipeline.execute_batch(batch)
        assert res.translated_count == 1
        item_res = res.item_results[0]
        assert item_res.status == TranslationStatus.TRANSLATED
        assert item_res.translation == "欢迎，{username}！"

    @pytest.mark.asyncio
    async def test_placeholder_repair_failure_marks_failed(self, fake_client):
        # 1. Batch call returns broken placeholder
        batch_resp = json.dumps({
            "translations": [
                {"id": "entry_fail", "translation": "你好 {用户}"},
            ]
        })
        fake_client.queue_response(batch_resp)

        # 2. Repair call returns still broken translation
        repair_resp1 = json.dumps({"translation": "你好 {玩家}"})
        repair_resp2 = json.dumps({"translation": "你好 {玩家2}"})
        fake_client.queue_response(repair_resp1)
        fake_client.queue_response(repair_resp2)

        pipeline = TranslationPipeline(
            client=fake_client,
            config=TranslationConfig(auto_repair=True, max_repairs=2),
        )

        batch = TranslationBatch(
            batch_index=0,
            items=[
                BatchItem(entry_id="entry_fail", target_key="msgid", text="Hello {user}"),
            ],
        )

        res = await pipeline.execute_batch(batch)
        assert res.failed_count == 1
        item_res = res.item_results[0]
        assert item_res.status == TranslationStatus.FAILED
        # Safe protection: corrupted translation MUST NOT be committed
        assert item_res.translation is None

        # Verify entry msgstr is untouched
        entry = TranslationEntry(id="entry_fail", msgid="Hello {user}")
        pipeline.apply_batch_result_to_entries(res, {"entry_fail": entry})
        assert entry.msgstr == ""
        assert entry.status == TranslationStatus.FAILED

    @pytest.mark.asyncio
    async def test_missing_item_id_marked_failed(self, fake_client):
        # Batch returns translation for item1 only, omits item2
        batch_resp = json.dumps({
            "translations": [
                {"id": "item1", "translation": "一"},
            ]
        })
        fake_client.queue_response(batch_resp)

        pipeline = TranslationPipeline(client=fake_client)
        batch = TranslationBatch(
            batch_index=0,
            items=[
                BatchItem(entry_id="item1", target_key="msgid", text="One"),
                BatchItem(entry_id="item2", target_key="msgid", text="Two"),
            ],
        )

        res = await pipeline.execute_batch(batch)
        assert res.translated_count == 1
        assert res.failed_count == 1
        assert res.item_results[1].status == TranslationStatus.FAILED
