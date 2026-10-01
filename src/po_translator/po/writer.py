"""PO/POT file writer with atomic writes and backup guarantees."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import polib

from po_translator.domain.models import PODocument
from po_translator.exceptions import POWriteError
from po_translator.po.mapper import POMapper


class POWriter:
    """Safely writes PODocument back to disk using atomic operations and validation."""

    @classmethod
    def write_file(
        cls,
        document: PODocument,
        target_path: Path | str,
        overwrite: bool = False,
        create_backup: bool = True,
        encoding: str = "utf-8",
    ) -> Path:
        """Write a PODocument to the target path.

        Workflow:
        1. Safeguard existing files against accidental overwrite.
        2. Generate temporary file in the same directory.
        3. Write PO content.
        4. Validate written temporary file with polib.
        5. Atomically rename temporary file to target path.
        6. Create .bak backup if overwriting an existing file.
        """
        target = Path(target_path).resolve()
        target_dir = target.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        if target.exists() and not overwrite:
            raise POWriteError(
                f"Target file already exists and overwrite is disabled: {target}"
            )

        # Prepare raw polib POFile instance
        raw_po: polib.POFile | None = getattr(document, "_raw_po_file", None)

        if raw_po is not None:
            # Map updated entries back into the existing raw_po
            entry_map = {e.id: e for e in document.entries}
            for po_entry in raw_po:
                dom = POMapper.to_domain(po_entry)
                if dom.id in entry_map:
                    POMapper.update_po_entry(po_entry, entry_map[dom.id])
            for obs in raw_po.obsolete_entries():
                dom = POMapper.to_domain(obs)
                if dom.id in entry_map:
                    POMapper.update_po_entry(obs, entry_map[dom.id])
            po_to_save = raw_po
        else:
            # Construct a clean polib POFile from domain document
            po_to_save = polib.POFile(encoding=encoding)
            po_to_save.metadata = dict(document.metadata)
            if document.header_comment:
                po_to_save.header = document.header_comment

            for entry in document.entries:
                flags_list = sorted(entry.flags)
                if entry.is_fuzzy and "fuzzy" not in flags_list:
                    flags_list.append("fuzzy")
                elif not entry.is_fuzzy and "fuzzy" in flags_list:
                    flags_list.remove("fuzzy")

                po_entry = polib.POEntry(
                    msgid=entry.msgid,
                    msgid_plural=entry.msgid_plural or "",
                    msgstr=entry.msgstr,
                    msgstr_plural=entry.msgstr_plural,
                    msgctxt=entry.msgctxt,
                    comment="\n".join(entry.comments),
                    tcomment="\n".join(entry.extracted_comments),
                    occurrences=entry.occurrences,
                    flags=flags_list,
                    obsolete=entry.is_obsolete,
                )
                po_to_save.append(po_entry)

        # Write to temporary file in the same directory (required for atomic rename on POSIX/Windows)
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=target_dir,
            prefix=f".tmp_{target.stem}_",
            suffix=".po",
        )
        os.close(temp_fd)
        temp_file = Path(temp_path_str)

        try:
            # Step 1: Save to temp file
            po_to_save.encoding = encoding
            po_to_save.save(fpath=str(temp_file))

            # Step 2: Validate written file can be parsed cleanly
            try:
                verified_po = polib.pofile(str(temp_file), encoding=encoding)
                if len(verified_po) != len(po_to_save):
                    raise POWriteError(
                        f"Validation mismatch: expected {len(po_to_save)} entries, got {len(verified_po)}"
                    )
            except Exception as val_err:
                raise POWriteError(f"Temporary file validation failed: {val_err}") from val_err

            # Step 3: Backup existing target if requested
            if target.exists() and create_backup:
                backup_path = target.with_suffix(target.suffix + ".bak")
                shutil.copy2(target, backup_path)

            # Step 4: Atomic rename/replace
            temp_file.replace(target)
            return target

        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            if isinstance(e, POWriteError):
                raise
            raise POWriteError(f"Failed to atomically write PO file to '{target}': {e}") from e
