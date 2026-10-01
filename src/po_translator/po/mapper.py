"""Mapper between polib POEntry and Domain TranslationEntry."""

from __future__ import annotations

import polib

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry, calculate_entry_id


class POMapper:
    """Provides bidirectional conversion between polib.POEntry and TranslationEntry."""

    @staticmethod
    def to_domain(entry: polib.POEntry) -> TranslationEntry:
        """Convert a polib.POEntry to a domain TranslationEntry."""
        flags_set = set(entry.flags) if entry.flags else set()
        is_fuzzy = "fuzzy" in flags_set
        is_obsolete = bool(entry.obsolete)

        # Normalize msgstr_plural dict {int: str}
        msgstr_plural: dict[int, str] = {}
        if entry.msgstr_plural:
            for k, v in entry.msgstr_plural.items():
                try:
                    msgstr_plural[int(k)] = v
                except (ValueError, TypeError):
                    pass

        # Compute stable deterministic ID
        entry_id = calculate_entry_id(
            msgid=entry.msgid,
            msgctxt=entry.msgctxt,
            msgid_plural=entry.msgid_plural,
            occurrences=entry.occurrences,
        )

        # Determine initial translation status
        status = TranslationStatus.PENDING
        has_trans = bool(entry.msgstr.strip()) or any(v.strip() for v in msgstr_plural.values())
        if is_obsolete:
            status = TranslationStatus.SKIPPED
        elif is_fuzzy:
            status = TranslationStatus.REVIEW_REQUIRED
        elif has_trans:
            status = TranslationStatus.TRANSLATED

        return TranslationEntry(
            id=entry_id,
            msgid=entry.msgid,
            msgid_plural=entry.msgid_plural or None,
            msgctxt=entry.msgctxt or None,
            msgstr=entry.msgstr or "",
            msgstr_plural=msgstr_plural,
            comments=list(entry.comment.splitlines()) if entry.comment else [],
            extracted_comments=list(entry.tcomment.splitlines()) if entry.tcomment else [],
            occurrences=[(str(f), str(l)) for f, l in entry.occurrences] if entry.occurrences else [],
            flags=flags_set,
            is_obsolete=is_obsolete,
            is_fuzzy=is_fuzzy,
            status=status,
        )

    @staticmethod
    def update_po_entry(po_entry: polib.POEntry, domain_entry: TranslationEntry) -> None:
        """Update a polib.POEntry with content from a domain TranslationEntry, preserving metadata."""
        po_entry.msgstr = domain_entry.msgstr

        if domain_entry.msgstr_plural:
            po_entry.msgstr_plural = {k: v for k, v in domain_entry.msgstr_plural.items()}

        # Flags synchronization
        flags_set = set(domain_entry.flags)
        if domain_entry.is_fuzzy:
            flags_set.add("fuzzy")
        else:
            flags_set.discard("fuzzy")

        po_entry.flags = sorted(flags_set)
        po_entry.obsolete = domain_entry.is_obsolete
