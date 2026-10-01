"""Domain models for PO LLM Translator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus


def calculate_entry_id(
    msgid: str,
    msgctxt: str | None = None,
    msgid_plural: str | None = None,
    occurrences: list[tuple[str, str]] | None = None,
) -> str:
    """Generate a stable, deterministic hash ID for a PO translation entry.

    The hash incorporates msgctxt, msgid, msgid_plural, and normalized occurrences
    to uniquely identify an entry independently of its line number or file position.
    """
    hasher = hashlib.sha256()
    hasher.update((msgctxt or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(msgid.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((msgid_plural or "").encode("utf-8"))
    hasher.update(b"\x00")

    if occurrences:
        # Sort occurrences to be order-independent
        norm_occ = sorted((str(f), str(l)) for f, l in occurrences)
        hasher.update(";".join(f"{f}:{l}" for f, l in norm_occ).encode("utf-8"))

    return hasher.hexdigest()[:16]


@dataclass
class TranslationEntry:
    """Core domain model representing a single translation unit from a PO file."""

    id: str
    msgid: str
    msgid_plural: str | None = None
    msgctxt: str | None = None

    msgstr: str = ""
    msgstr_plural: dict[int, str] = field(default_factory=dict)

    comments: list[str] = field(default_factory=list)
    extracted_comments: list[str] = field(default_factory=list)
    occurrences: list[tuple[str, str]] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    is_obsolete: bool = False
    is_fuzzy: bool = False

    status: TranslationStatus = TranslationStatus.PENDING

    @property
    def is_plural(self) -> bool:
        """Return True if this entry represents a plural form."""
        return bool(self.msgid_plural)

    @property
    def has_translation(self) -> bool:
        """Check whether the entry already has non-empty translation."""
        if self.is_plural:
            return bool(self.msgstr_plural and any(val.strip() for val in self.msgstr_plural.values()))
        return bool(self.msgstr and self.msgstr.strip())

    def is_candidate_for_translation(
        self,
        mode: FilterMode = FilterMode.UNTRANSLATED_ONLY,
        fuzzy_handling: FuzzyHandling = FuzzyHandling.SKIP,
    ) -> bool:
        """Determine whether this entry should be translated based on settings.

        Follows requirements:
        - msgid must not be empty (empty msgid is header)
        - not obsolete
        - untranslated only vs all vs fuzzy only
        - obeys fuzzy handling strategy
        """
        if not self.msgid.strip():
            return False

        if self.is_obsolete:
            return False

        if self.is_fuzzy:
            if fuzzy_handling == FuzzyHandling.SKIP:
                return False
            if fuzzy_handling == FuzzyHandling.REVIEW:
                return False
            # FuzzyHandling.RETRANSLATE allows fuzzy entries to be translated
            if mode == FilterMode.FUZZY_ONLY:
                return True

        if mode == FilterMode.FUZZY_ONLY:
            return self.is_fuzzy

        if mode == FilterMode.UNTRANSLATED_ONLY:
            return not self.has_translation or (self.is_fuzzy and fuzzy_handling == FuzzyHandling.RETRANSLATE)

        return mode == FilterMode.ALL


@dataclass
class PODocument:
    """In-memory representation of a complete PO/POT document."""

    entries: list[TranslationEntry] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    header_comment: str | None = None
    path: Path | None = None
    encoding: str = "utf-8"

    def get_entry_by_id(self, entry_id: str) -> TranslationEntry | None:
        """Find an entry by its unique ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    @property
    def translatable_entries(self) -> list[TranslationEntry]:
        """Return active entries that are not obsolete and not headers."""
        return [e for e in self.entries if e.msgid.strip() and not e.is_obsolete]
