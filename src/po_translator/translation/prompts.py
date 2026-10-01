"""Prompt loading and management module."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

TRANSLATE_PROMPT_VERSION = "1.0"
REPAIR_PROMPT_VERSION = "1.0"


def load_prompt_template(filename: str) -> str:
    """Load prompt template text from prompts directory with UTF-8 encoding."""
    target_path = PROMPTS_DIR / filename
    if not target_path.is_file():
        raise FileNotFoundError(f"Prompt template file not found: {target_path}")
    return target_path.read_text(encoding="utf-8")


def build_translate_system_prompt(
    source_lang: str,
    target_lang: str,
    glossary_terms: list[tuple[str, str]] | None = None,
) -> str:
    """Construct full system prompt for batch translation."""
    template = load_prompt_template("translate_system.txt")

    if glossary_terms:
        glossary_lines = [
            "- Only apply glossary terms when the source text contains the corresponding source term:"
        ]
        for src, tgt in glossary_terms:
            glossary_lines.append(f"  * {src} -> {tgt}")
        glossary_section = "\n".join(glossary_lines)
    else:
        glossary_section = "- No project glossary terms applicable for this batch."

    return (
        template.replace("{source_lang}", source_lang)
        .replace("{target_lang}", target_lang)
        .replace("{glossary_section}", glossary_section)
    )


def build_repair_system_prompt(
    source_text: str,
    incorrect_translation: str,
    required_placeholders: list[str],
    detected_issues: list[str],
) -> str:
    """Construct prompt for targeted placeholder / format repair."""
    template = load_prompt_template("repair_system.txt")
    req_ph_str = ", ".join(f"'{p}'" for p in required_placeholders) if required_placeholders else "None"
    issues_str = "\n".join(f"- {iss}" for iss in detected_issues) if detected_issues else "None"

    return (
        template.replace("{source_text}", source_text)
        .replace("{incorrect_translation}", incorrect_translation)
        .replace("{required_placeholders}", req_ph_str)
        .replace("{detected_issues}", issues_str)
    )
