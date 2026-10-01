"""Command-line interface for PO LLM Translator."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationMode
from po_translator.exceptions import POTranslatorError
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.models import LLMProfile
from po_translator.po.reader import POReader
from po_translator.services.translation_service import TranslationService
from po_translator.translation.pipeline import TranslationConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="po-translator",
        description="Industrial LLM-assisted localization tool for GNU gettext PO/POT files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Translate Command
    trans_p = subparsers.add_parser("translate", help="Translate a PO file using LLM.")
    trans_p.add_argument("file", help="Path to input .po / .pot file")
    trans_p.add_argument("-s", "--source", default="en", help="Source language code (default: en)")
    trans_p.add_argument("-t", "--target", default="zh-CN", help="Target language code (default: zh-CN)")
    trans_p.add_argument("-o", "--output", default=None, help="Output file path (default: <name>.translated.po)")
    trans_p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    trans_p.add_argument("--api-key", default=None, help="API Key (or set OPENAI_API_KEY environment variable)")
    trans_p.add_argument("--model", default="gpt-4o", help="Model name (default: gpt-4o)")
    trans_p.add_argument("--mode", choices=["fast", "quality", "smart"], default="smart", help="Translation mode")
    trans_p.add_argument("--overwrite", action="store_true", help="Allow overwriting target file")

    # 2. Analyze Command
    ana_p = subparsers.add_parser("analyze", help="Analyze PO file statistics.")
    ana_p.add_argument("file", help="Path to input .po / .pot file")

    return parser


def run_analyze(file_path: str) -> int:
    try:
        doc = POReader.read_file(file_path)
    except (POTranslatorError, OSError) as e:
        print(f"Error parsing PO file: {e}", file=sys.stderr)
        return 1

    total = len(doc.entries)
    untranslated = sum(1 for e in doc.entries if not e.has_translation and not e.is_obsolete)
    fuzzy = sum(1 for e in doc.entries if e.is_fuzzy)
    plural = sum(1 for e in doc.entries if e.is_plural)
    obsolete = sum(1 for e in doc.entries if e.is_obsolete)

    print("=== PO File Analysis ===")
    print(f"File:           {file_path}")
    print(f"Total Entries:  {total}")
    print(f"Untranslated:   {untranslated}")
    print(f"Fuzzy:          {fuzzy}")
    print(f"Plural forms:   {plural}")
    print(f"Obsolete:       {obsolete}")
    print(f"Metadata items: {len(doc.metadata)}")
    return 0


async def run_translate(args: argparse.Namespace) -> int:
    input_file = Path(args.file)
    if not input_file.is_file():
        print(f"Error: Input file does not exist: {input_file}", file=sys.stderr)
        return 1

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    profile = LLMProfile(
        name="cli",
        base_url=base_url,
        api_key=api_key,
        model=args.model,
    )

    client = OpenAICompatibleClient(profile)
    service = TranslationService(client=client)

    config = TranslationConfig(
        source_lang=args.source,
        target_lang=args.target,
        mode=TranslationMode(args.mode),
    )

    def on_progress(current: int, total: int) -> None:
        pct = (current / total) * 100 if total > 0 else 100
        print(f"Progress: [{current}/{total}] batches completed ({pct:.1f}%)")

    print(f"Translating '{input_file.name}' ({args.source} -> {args.target})...")

    try:
        out_path, summary = await service.translate_file(
            input_file=input_file,
            output_file=args.output,
            config=config,
            filter_mode=FilterMode.UNTRANSLATED_ONLY,
            fuzzy_handling=FuzzyHandling.SKIP,
            overwrite=args.overwrite,
            progress_callback=on_progress,
        )
    except (POTranslatorError, OSError) as e:
        print(f"Translation failed: {e}", file=sys.stderr)
        return 1

    print("\n=== Translation Completed Successfully ===")
    print(f"Saved to:    {out_path}")
    print(f"Translated:  {summary.translated_count}")
    print(f"Failed:      {summary.failed_count}")
    print(f"Review req:  {summary.review_count}")
    print(f"Skipped:     {summary.skipped_count}")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        sys.exit(run_analyze(args.file))
    elif args.command == "translate":
        exit_code = asyncio.run(run_translate(args))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
