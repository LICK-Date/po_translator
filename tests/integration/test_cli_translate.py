"""Integration tests for TranslationService and CLI workflows."""

from pathlib import Path

import pytest

from po_translator.cli import build_parser, run_analyze
from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus
from po_translator.llm.fake_client import FakeLLMClient
from po_translator.po.reader import POReader
from po_translator.services.translation_service import TranslationService

FIXTURE_PO = Path(__file__).resolve().parent.parent / "fixtures" / "sample.po"


class TestCLITranslateIntegration:
    def test_cli_parser_build(self):
        parser = build_parser()
        args = parser.parse_args(["translate", "game.po", "-s", "ja", "-t", "zh-CN", "--mode", "fast"])
        assert args.command == "translate"
        assert args.file == "game.po"
        assert args.source == "ja"
        assert args.target == "zh-CN"
        assert args.mode == "fast"

    def test_cli_analyze_command(self, capsys):
        exit_code = run_analyze(str(FIXTURE_PO))
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PO File Analysis" in captured.out
        assert "Total Entries:  8" in captured.out
        assert "Untranslated:" in captured.out

    @pytest.mark.asyncio
    async def test_end_to_end_file_translation(self, tmp_path):
        """End-to-end translation of sample.po -> sample.translated.po using FakeLLMClient."""
        fake_client = FakeLLMClient()
        service = TranslationService(client=fake_client)

        out_po = tmp_path / "sample.translated.po"

        saved_path, summary = await service.translate_file(
            input_file=FIXTURE_PO,
            output_file=out_po,
            filter_mode=FilterMode.UNTRANSLATED_ONLY,
            fuzzy_handling=FuzzyHandling.SKIP,
            overwrite=True,
        )

        assert saved_path == out_po
        assert out_po.exists()
        assert summary.translated_count > 0

        # Reload and inspect translated document
        reloaded = POReader.read_file(out_po)
        assert len(reloaded.entries) == 8

        # 1. Existing translation "Open" ("打开") must be untouched
        existing_e = next(e for e in reloaded.entries if e.msgid == "Open")
        assert existing_e.msgstr == "打开"

        # 2. Fuzzy entry must be skipped by default
        fuzzy_e = next(e for e in reloaded.entries if e.is_fuzzy)
        assert fuzzy_e.status == TranslationStatus.REVIEW_REQUIRED

        # 3. Untranslated entries should now have translations
        hello_e = next(e for e in reloaded.entries if e.msgid == "Hello World")
        assert hello_e.status == TranslationStatus.TRANSLATED
        assert "Translated: Hello World" in hello_e.msgstr

        # 4. Metadata preserved
        assert reloaded.metadata["Project-Id-Version"] == "Sample 1.0"
