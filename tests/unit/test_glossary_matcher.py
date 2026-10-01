"""Unit tests for GlossaryMatcher."""

from po_translator.terminology.matcher import GlossaryMatcher
from po_translator.terminology.models import Glossary, GlossaryTerm


class TestGlossaryMatcher:
    def test_cjk_term_matching(self):
        glossary = Glossary([
            GlossaryTerm(id="1", source="魔导石", target="Magic Stone"),
            GlossaryTerm(id="2", source="圣骑士", target="Paladin"),
            GlossaryTerm(id="3", source="王都", target="Royal Capital"),
        ])

        text = "勇敢的圣骑士在王都寻找传说中的魔导石。"
        matches = GlossaryMatcher.match_text(text, glossary)
        matched_sources = [m.source for m in matches]

        assert "圣骑士" in matched_sources
        assert "王都" in matched_sources
        assert "魔导石" in matched_sources

    def test_english_word_boundary_matching(self):
        glossary = Glossary([
            GlossaryTerm(id="1", source="Artifact", target="圣遗物"),
            GlossaryTerm(id="2", source="Rate", target="比率"),
        ])

        # Exact word "Artifact" matches, "Artifacts" or "Operating" won't mistakenly trigger
        text = "Equip your Artifact to increase CRIT Rate."
        matches = GlossaryMatcher.match_text(text, glossary)
        sources = [m.source for m in matches]

        assert "Artifact" in sources
        assert "Rate" in sources

    def test_match_batch_aggregation(self):
        glossary = Glossary([
            GlossaryTerm(id="1", source="Item", target="道具"),
            GlossaryTerm(id="2", source="Skill", target="技能"),
            GlossaryTerm(id="3", source="Map", target="地图"),
        ])

        batch = ["Open Item menu", "Upgrade your Skill"]
        matches = GlossaryMatcher.match_batch(batch, glossary)
        matched_sources = [m.source for m in matches]

        assert "Item" in matched_sources
        assert "Skill" in matched_sources
        assert "Map" not in matched_sources
