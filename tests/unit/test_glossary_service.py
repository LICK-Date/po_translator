"""Unit tests for Glossary models and GlossaryService."""

import json

import pytest

from po_translator.domain.models import PODocument, TranslationEntry
from po_translator.llm.fake_client import FakeLLMClient
from po_translator.services.glossary_service import GlossaryService
from po_translator.terminology.models import (
    Glossary,
    GlossaryTerm,
    TermOrigin,
)


class TestGlossaryModelPriority:
    def test_locked_term_protection(self):
        glossary = Glossary()
        user_term = GlossaryTerm(
            id="1",
            source="魔导石",
            target="Custom Stone",
            locked=True,
            created_by=TermOrigin.USER,
        )
        glossary.add_term(user_term)

        # Attempt to overwrite with lower-priority LLM term
        llm_term = GlossaryTerm(
            id="1",
            source="魔导石",
            target="Magic Stone",
            locked=False,
            created_by=TermOrigin.LLM,
        )
        updated = glossary.add_term(llm_term, overwrite_locked=False)
        assert updated is False
        assert glossary.get("魔导石").target == "Custom Stone"

    def test_priority_hierarchy_upgrade(self):
        glossary = Glossary()
        algo_term = GlossaryTerm(
            id="1",
            source="Gold",
            target=None,
            created_by=TermOrigin.ALGORITHM,
        )
        glossary.add_term(algo_term)

        # LLM term should upgrade algorithm term
        llm_term = GlossaryTerm(
            id="1",
            source="Gold",
            target="金币",
            created_by=TermOrigin.LLM,
        )
        assert glossary.add_term(llm_term) is True
        assert glossary.get("Gold").target == "金币"
        assert glossary.get("Gold").created_by == TermOrigin.LLM


class TestGlossaryService:
    @pytest.mark.asyncio
    async def test_auto_build_glossary(self):
        fake_client = FakeLLMClient()

        # 1. First canned response: LLM filter approving the candidate
        filter_resp = json.dumps({
            "terms": [
                {"source": "Goblin King", "keep": True, "category": "boss", "reason": "Boss enemy name"},
            ]
        })
        # 2. Second canned response: LLM translation of approved term
        translate_resp = json.dumps({
            "translations": [
                {"source": "Goblin King", "target": "哥布林王"},
            ]
        })

        fake_client.queue_response(filter_resp)
        fake_client.queue_response(translate_resp)

        doc = PODocument(entries=[
            TranslationEntry(id="1", msgid="Defeat the Goblin King in battle."),
            TranslationEntry(id="2", msgid="The Goblin King drops rare loot."),
        ])

        service = GlossaryService()
        glossary = await service.auto_build_glossary(
            document=doc,
            source_lang="en",
            target_lang="zh-CN",
            client=fake_client,
        )

        assert len(glossary) == 1
        term = glossary.get("Goblin King")
        assert term is not None
        assert term.target == "哥布林王"
        assert term.category == "boss"

    def test_match_batch_terms(self):
        glossary = Glossary([
            GlossaryTerm(id="1", source="Gold", target="金币"),
            GlossaryTerm(id="2", source="Silver", target="银币"),
            GlossaryTerm(id="3", source="Copper", target=None),  # Untranslated term
        ])

        service = GlossaryService()
        batch = ["You earned 100 Gold and 50 Silver.", "No other coins."]
        matches = service.match_batch_terms(batch, glossary)

        assert ("Gold", "金币") in matches
        assert ("Silver", "银币") in matches
        assert ("Copper", None) not in matches
