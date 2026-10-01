"""Placeholder extraction and validation engine.

Deterministic protection and validation for variables, format specifiers,
tags, escape sequences, and game variables in localization strings.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum


class PlaceholderType(str, Enum):
    """Categorized placeholder type."""
    PRINTF = "printf"
    PYTHON_FORMAT = "python_format"
    HTML_TAG = "html_tag"
    ESCAPE = "escape"
    GAME_VARIABLE = "game_variable"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Placeholder:
    """Representation of an extracted placeholder in a text string."""
    raw: str
    placeholder_type: PlaceholderType
    start: int
    end: int
    normalized_key: str = ""

    def __post_init__(self) -> None:
        if not self.normalized_key:
            object.__setattr__(self, "normalized_key", self.raw)


@dataclass
class PlaceholderIssue:
    """Details of a validation issue with placeholders."""
    issue_type: str  # "missing", "extra", "changed", "count_mismatch"
    placeholder: str
    message: str


@dataclass
class PlaceholderValidationResult:
    """Outcome of validating placeholders between source and translation."""
    is_valid: bool
    issues: list[PlaceholderIssue] = field(default_factory=list)
    source_placeholders: list[Placeholder] = field(default_factory=list)
    translation_placeholders: list[Placeholder] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return not self.is_valid or len(self.issues) > 0


# Precompiled regex patterns

# 1. Double curly braces game variable or template, e.g., {{player}}
RE_DOUBLE_CURLY = re.compile(r"\{\{[a-zA-Z0-9_\-.]+\}\}")

# 2. Python format, e.g., {}, {0}, {name}, {name!r}, {name:.2f}, {0:02d}
RE_PY_FORMAT = re.compile(r"\{[a-zA-Z0-9_]*(?:![rsa])?(?::[^{}]+)?\}")

# 3. Printf-style, e.g., %s, %d, %1$s, %(name)s, %-10.2f, %%
RE_PRINTF = re.compile(
    r"%(?:\((?P<k>[^)]+)\))?"  # %(name)s
    r"(?:(?P<pos>\d+)\$)?"     # %1$s
    r"[-+ 0#]*"                # flags
    r"(?:\d+|\*)?"             # width
    r"(?:\.(?:\d+|\*))?"       # precision
    r"(?:[hlLzjt]|\d+)*"       # length modifiers
    r"[diouxXeEfFgGaAcspnm%]"  # conversion type
)

# 4. Escape sequences, e.g., \n, \t, \r, \\
RE_ESCAPE = re.compile(r"\\(?:n|t|r|\\)")

# 5. HTML / XML tags, e.g., <b>, </b>, <color=red>, <size=14>, <br/>
RE_HTML_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9_\-:.]*(?:\s*=\s*['\"][^'\"]*['\"]|\s*=\s*[^<>'\"]+|\s+[^<>]*)*/?>")

# 6. Common game variables, e.g., [PLAYER], <PLAYER>, $player, ${player}
RE_GAME_BRACKET = re.compile(r"\[[A-Z0-9_]{2,}\]")
RE_GAME_TAG = re.compile(r"<[A-Z0-9_]{2,}>")
RE_GAME_DOLLAR_BRACE = re.compile(r"\$\{[a-zA-Z0-9_]+\}")
RE_GAME_DOLLAR_WORD = re.compile(r"\$[a-zA-Z0-9_]+")


def extract_placeholders(
    text: str,
    custom_patterns: Sequence[str] | None = None,
) -> list[Placeholder]:
    """Extract all format specifiers, placeholders, and tags from text.

    Uses an ordered scan to prevent sub-pattern collisions. Returns placeholders
    sorted by their appearance in the text.
    """
    if not text:
        return []

    spans_occupied: list[tuple[int, int]] = []
    placeholders: list[Placeholder] = []

    def is_overlapping(start: int, end: int) -> bool:
        return any(s < end and end > s and not (end <= s or start >= e) for s, e in spans_occupied)

    # Helper to register matches
    def record_match(match: re.Match, p_type: PlaceholderType, key: str | None = None) -> None:
        start, end = match.span()
        if not is_overlapping(start, end):
            spans_occupied.append((start, end))
            raw = match.group(0)
            norm_key = key if key is not None else raw
            placeholders.append(
                Placeholder(
                    raw=raw,
                    placeholder_type=p_type,
                    start=start,
                    end=end,
                    normalized_key=norm_key,
                )
            )

    # 1. Custom patterns first if provided
    if custom_patterns:
        for pat in custom_patterns:
            for m in re.finditer(pat, text):
                record_match(m, PlaceholderType.CUSTOM)

    # 2. Escape sequences (\n, \t, \r, \\)
    for m in RE_ESCAPE.finditer(text):
        record_match(m, PlaceholderType.ESCAPE)

    # 3. Double curly braces (must take precedence over single curly)
    for m in RE_DOUBLE_CURLY.finditer(text):
        record_match(m, PlaceholderType.GAME_VARIABLE)

    # 4. Game variables with braces (${var}, [PLAYER], <PLAYER>)
    for m in RE_GAME_DOLLAR_BRACE.finditer(text):
        record_match(m, PlaceholderType.GAME_VARIABLE)

    for m in RE_GAME_BRACKET.finditer(text):
        record_match(m, PlaceholderType.GAME_VARIABLE)

    for m in RE_GAME_TAG.finditer(text):
        record_match(m, PlaceholderType.GAME_VARIABLE)

    # 5. Printf format specifiers
    for m in RE_PRINTF.finditer(text):
        record_match(m, PlaceholderType.PRINTF)

    # 6. Python format specifiers
    for m in RE_PY_FORMAT.finditer(text):
        record_match(m, PlaceholderType.PYTHON_FORMAT)

    # 7. Game variables without braces ($word)
    for m in RE_GAME_DOLLAR_WORD.finditer(text):
        record_match(m, PlaceholderType.GAME_VARIABLE)

    # 8. HTML / XML tags
    for m in RE_HTML_TAG.finditer(text):
        record_match(m, PlaceholderType.HTML_TAG)

    placeholders.sort(key=lambda p: p.start)
    return placeholders


def validate_placeholders(
    source: str,
    translation: str,
    custom_patterns: Sequence[str] | None = None,
) -> PlaceholderValidationResult:
    """Validate that translation strictly preserves placeholders from source.

    Checks for:
    - Missing placeholders (present in source but absent in translation)
    - Extra placeholders (present in translation but absent in source)
    - Count mismatches (duplicated or dropped occurrences)
    - Translated placeholder names (e.g. {username} -> {用户名})
    """
    src_ph = extract_placeholders(source, custom_patterns)
    trans_ph = extract_placeholders(translation, custom_patterns)

    issues: list[PlaceholderIssue] = []

    src_counts = Counter(p.raw for p in src_ph)
    trans_counts = Counter(p.raw for p in trans_ph)

    # Check for missing or count mismatches
    for raw, count in src_counts.items():
        actual_count = trans_counts.get(raw, 0)
        if actual_count == 0:
            issues.append(
                PlaceholderIssue(
                    issue_type="missing",
                    placeholder=raw,
                    message=f"Placeholder '{raw}' is missing in translation.",
                )
            )
        elif actual_count < count:
            issues.append(
                PlaceholderIssue(
                    issue_type="count_mismatch",
                    placeholder=raw,
                    message=f"Placeholder '{raw}' appears {actual_count} time(s) in translation, expected {count}.",
                )
            )

    # Check for extra or excessive placeholders
    for raw, actual_count in trans_counts.items():
        expected_count = src_counts.get(raw, 0)
        if expected_count == 0:
            issues.append(
                PlaceholderIssue(
                    issue_type="extra",
                    placeholder=raw,
                    message=f"Unexpected placeholder '{raw}' appears in translation.",
                )
            )
        elif actual_count > expected_count:
            issues.append(
                PlaceholderIssue(
                    issue_type="count_mismatch",
                    placeholder=raw,
                    message=f"Placeholder '{raw}' appears {actual_count} time(s) in translation, expected {expected_count}.",
                )
            )

    # Identify potential corrupted/translated placeholders
    # e.g., source has {username} and translation has {用户名}
    # Match standalone single curly braces only, excluding {{var}} and ${var}
    trans_curly_all = re.findall(r"(?<![\$\{])\{[^{}]+\}(?!\})", translation)
    for curly in trans_curly_all:
        if curly not in trans_counts:
            # Found an unextracted curly block, likely translated or corrupted variable name
            issues.append(
                PlaceholderIssue(
                    issue_type="changed",
                    placeholder=curly,
                    message=f"Corrupted or translated variable syntax detected: '{curly}'.",
                )
            )

    is_valid = len(issues) == 0
    return PlaceholderValidationResult(
        is_valid=is_valid,
        issues=issues,
        source_placeholders=src_ph,
        translation_placeholders=trans_ph,
    )
