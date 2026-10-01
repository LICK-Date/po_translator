"""Unit and integration tests for POReader and POWriter."""

from pathlib import Path

import pytest

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus
from po_translator.domain.models import calculate_entry_id
from po_translator.exceptions import POWriteError
from po_translator.po.reader import POReader
from po_translator.po.writer import POWriter

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample.po"


class TestPOReaderAndWriter:
    def test_read_sample_po(self):
        doc = POReader.read_file(FIXTURE_PATH)
        assert len(doc.entries) == 8
        assert "Project-Id-Version" in doc.metadata
        assert doc.metadata["Project-Id-Version"] == "Sample 1.0"
        assert "Plural-Forms" in doc.metadata

        # Find entry with plural
        plural_entry = next(e for e in doc.entries if e.is_plural)
        assert plural_entry.msgid == "You found a coin."
        assert plural_entry.msgid_plural == "You found %d coins."
        assert plural_entry.msgstr_plural[0] == "你找到了一个硬币。"
        assert plural_entry.msgstr_plural[1] == "你找到了 %d 个硬币。"

        # Find fuzzy entry
        fuzzy_entry = next(e for e in doc.entries if e.is_fuzzy)
        assert fuzzy_entry.msgid == "Defeat the goblin king"
        assert "fuzzy" in fuzzy_entry.flags
        assert fuzzy_entry.status == TranslationStatus.REVIEW_REQUIRED

        # Find context entry
        ctx_entry = next(e for e in doc.entries if e.msgctxt == "menu")
        assert ctx_entry.msgid == "Open"
        assert ctx_entry.msgstr == "打开"

    def test_po_round_trip_lossless(self, tmp_path):
        """Read original PO -> write unchanged -> read again, verify integrity."""
        orig_doc = POReader.read_file(FIXTURE_PATH)
        out_file = tmp_path / "round_trip.po"

        POWriter.write_file(orig_doc, out_file)

        # Reopen saved file
        reloaded_doc = POReader.read_file(out_file)

        assert len(reloaded_doc.entries) == len(orig_doc.entries)
        assert reloaded_doc.metadata == orig_doc.metadata

        for orig_e, reload_e in zip(orig_doc.entries, reloaded_doc.entries):
            assert orig_e.id == reload_e.id
            assert orig_e.msgid == reload_e.msgid
            assert orig_e.msgid_plural == reload_e.msgid_plural
            assert orig_e.msgctxt == reload_e.msgctxt
            assert orig_e.msgstr == reload_e.msgstr
            assert orig_e.msgstr_plural == reload_e.msgstr_plural
            assert orig_e.is_fuzzy == reload_e.is_fuzzy
            assert orig_e.comments == reload_e.comments
            assert orig_e.extracted_comments == reload_e.extracted_comments
            assert orig_e.occurrences == reload_e.occurrences
            assert orig_e.flags == reload_e.flags

    def test_writer_overwrite_protection_and_backup(self, tmp_path):
        doc = POReader.read_file(FIXTURE_PATH)
        target = tmp_path / "test.po"

        # First write succeeds
        POWriter.write_file(doc, target)
        assert target.exists()

        # Second write without overwrite fails
        with pytest.raises(POWriteError, match="overwrite is disabled"):
            POWriter.write_file(doc, target, overwrite=False)

        # Update entry msgstr
        untranslated = next(e for e in doc.entries if not e.has_translation)
        untranslated.msgstr = "你好世界"

        # Second write with overwrite and backup succeeds
        POWriter.write_file(doc, target, overwrite=True, create_backup=True)
        backup = target.with_suffix(".po.bak")
        assert backup.exists()

        # Check new content is saved
        reloaded = POReader.read_file(target)
        updated_e = reloaded.get_entry_by_id(untranslated.id)
        assert updated_e is not None
        assert updated_e.msgstr == "你好世界"

    def test_deterministic_entry_id(self):
        id1 = calculate_entry_id("Test message", msgctxt="menu", occurrences=[("ui.c", "10")])
        id2 = calculate_entry_id("Test message", msgctxt="menu", occurrences=[("ui.c", "10")])
        id_diff = calculate_entry_id("Test message", msgctxt="dialog", occurrences=[("ui.c", "10")])

        assert id1 == id2
        assert id1 != id_diff

    def test_candidate_filtering(self):
        doc = POReader.read_file(FIXTURE_PATH)
        entries = doc.entries

        # Untranslated only (default skips fuzzy)
        cands_untranslated = [
            e for e in entries
            if e.is_candidate_for_translation(FilterMode.UNTRANSLATED_ONLY, FuzzyHandling.SKIP)
        ]
        assert all(not e.has_translation and not e.is_fuzzy for e in cands_untranslated)

        # Fuzzy only
        cands_fuzzy = [
            e for e in entries
            if e.is_candidate_for_translation(FilterMode.FUZZY_ONLY, FuzzyHandling.RETRANSLATE)
        ]
        assert len(cands_fuzzy) == 1
        assert cands_fuzzy[0].is_fuzzy is True

        # All translatable entries
        cands_all = [
            e for e in entries
            if e.is_candidate_for_translation(FilterMode.ALL, FuzzyHandling.RETRANSLATE)
        ]
        assert len(cands_all) == len(entries)
