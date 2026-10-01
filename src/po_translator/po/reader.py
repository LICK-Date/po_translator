"""PO/POT file reader based on polib."""

from __future__ import annotations

from pathlib import Path

import polib

from po_translator.domain.models import PODocument
from po_translator.exceptions import POParseError
from po_translator.po.mapper import POMapper


class POReader:
    """Safely reads GNU gettext PO/POT files and transforms them into domain models."""

    @classmethod
    def read_file(cls, file_path: Path | str, encoding: str = "utf-8") -> PODocument:
        """Parse a .po or .pot file and return a PODocument."""
        p = Path(file_path)
        if not p.is_file():
            raise POParseError(f"Target PO file does not exist: {p}")

        try:
            # polib.pofile with explicit encoding
            po_file = polib.pofile(str(p), encoding=encoding)
        except Exception as e:
            raise POParseError(f"Failed to parse PO file '{p}': {e}") from e

        entries = []
        for entry in po_file:
            domain_entry = POMapper.to_domain(entry)
            entries.append(domain_entry)

        # Include obsolete entries if any
        for obs in po_file.obsolete_entries():
            obs_entry = POMapper.to_domain(obs)
            entries.append(obs_entry)

        doc = PODocument(
            entries=entries,
            metadata=dict(po_file.metadata),
            header_comment=po_file.header,
            path=p,
            encoding=encoding,
        )

        # Stash raw po_file reference for zero-loss round-trip writeback
        doc._raw_po_file = po_file

        return doc
