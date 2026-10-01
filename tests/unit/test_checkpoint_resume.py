"""Unit and integration tests for crash checkpointing and task resumption."""

import json

import pytest

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import PODocument, TranslationEntry
from po_translator.llm.fake_client import FakeLLMClient
from po_translator.po.writer import POWriter
from po_translator.services.project_service import ProjectService
from po_translator.storage.database import DatabaseManager


class TestCheckpointAndResume:
    @pytest.mark.asyncio
    async def test_resume_skips_already_translated_entries(self, tmp_path):
        db = DatabaseManager(":memory:")
        service = ProjectService(db)

        # 1. Create a dummy PO file with 4 untranslated entries
        test_po = tmp_path / "resume_test.po"
        initial_doc = PODocument(entries=[
            TranslationEntry(id="e1", msgid="One"),
            TranslationEntry(id="e2", msgid="Two"),
            TranslationEntry(id="e3", msgid="Three"),
            TranslationEntry(id="e4", msgid="Four"),
        ])
        POWriter.write_file(initial_doc, test_po)

        # 2. Register project in database
        project, doc = service.create_project(
            name="ResumeTest",
            po_path=test_po,
            source_lang="en",
            target_lang="zh-CN",
        )
        e1, e2, e3, e4 = doc.entries

        # 3. Simulate that Batch 1 (e1, e2) was completed and checkpointed before a crash
        service.entry_repo.checkpoint_batch_results(
            project.id,
            [
                (e1.id, TranslationStatus.TRANSLATED, "一"),
                (e2.id, TranslationStatus.TRANSLATED, "二"),
            ],
        )

        # Also store e1 in Translation Memory
        service.translation_memory.store("en", "zh-CN", "One", "一")

        # 4. Now simulate resuming the project after crash/restart
        # Fake LLM client only needs to receive requests for remaining entries (e3, e4)
        fake_client = FakeLLMClient()
        batch_resp = json.dumps({
            "translations": [
                {"id": e3.id, "translation": "三"},
                {"id": e4.id, "translation": "四"},
            ]
        })
        fake_client.queue_response(batch_resp)

        out_po = tmp_path / "resume_test.translated.po"
        saved_path, summary = await service.run_or_resume_project(
            project_id=project.id,
            client=fake_client,
            output_file=out_po,
        )

        assert saved_path == out_po
        # Only 2 entries (e3, e4) were eligible and translated
        assert summary.translatable_entries == 2
        assert summary.translated_count == 2

        # 5. Verify LLM request history: e1 and e2 MUST NOT be present in fake_client call
        assert len(fake_client.call_history) == 1
        sent_content = fake_client.call_history[0].messages[0].content
        data = json.loads(sent_content)
        sent_ids = [item["id"] for item in data["entries"]]

        assert e1.id not in sent_ids
        assert e2.id not in sent_ids
        assert e3.id in sent_ids
        assert e4.id in sent_ids
