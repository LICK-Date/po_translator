"""Unit tests for TermExtractor."""

from po_translator.domain.models import TranslationEntry
from po_translator.terminology.extractor import TermExtractor


class TestTermExtractor:
    def test_clean_text_strips_placeholders(self):
        extractor = TermExtractor()
        text = "Hello {username}! Click <b><color=red>START</color></b> now.\\nScore: %d."
        cleaned = extractor.clean_text(text)
        assert "{username}" not in cleaned
        assert "<b>" not in cleaned
        assert "%d" not in cleaned
        assert "Hello" in cleaned
        assert "START" in cleaned

    def test_extract_english_title_terms(self):
        extractor = TermExtractor(min_freq=2)
        entries = [
            TranslationEntry(id="1", msgid="Find the Goblin King in the dungeon."),
            TranslationEntry(id="2", msgid="Defeat the Goblin King to get loot."),
            TranslationEntry(id="3", msgid="The Magic Stone glows bright."),
            TranslationEntry(id="4", msgid="Use the Magic Stone at the altar."),
            TranslationEntry(id="5", msgid="Single occurrence Word here."),
        ]

        cands = extractor.extract_from_entries(entries, lang="en")
        terms = [c.text for c in cands]

        assert "Goblin King" in terms
        assert "Magic Stone" in terms
        assert "Single occurrence" not in terms

    def test_extract_chinese_terms(self):
        extractor = TermExtractor(min_freq=2, min_length=2, max_length=4)
        entries = [
            TranslationEntry(id="1", msgid="装备强化成功，等级提升。"),
            TranslationEntry(id="2", msgid="装备强化失败，金币扣除。"),
            TranslationEntry(id="3", msgid="进行普通攻击。"),
        ]

        cands = extractor.extract_from_entries(entries, lang="zh")
        texts = [c.text for c in cands]

        assert "装备强化" in texts
        assert any("强化" in t for t in texts)
