"""Translation Memory (TM) cache implementation."""

from __future__ import annotations

import hashlib

from po_translator.storage.database import DatabaseManager


def compute_tm_key(
    source_lang: str,
    target_lang: str,
    msgid: str,
    msgctxt: str | None = None,
    glossary_hash: str = "",
    prompt_version: str = "1.0",
) -> str:
    """Compute a deterministic SHA-256 fingerprint for Translation Memory caching."""
    hasher = hashlib.sha256()
    hasher.update(source_lang.strip().lower().encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(target_lang.strip().lower().encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((msgctxt or "").strip().encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(msgid.strip().encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(glossary_hash.strip().encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(prompt_version.strip().encode("utf-8"))
    return hasher.hexdigest()


class TranslationMemory:
    """Translation Memory persistent storage preventing redundant LLM requests."""

    def __init__(self, db: DatabaseManager, enabled: bool = True) -> None:
        self.db = db
        self.enabled = enabled

    def lookup(
        self,
        source_lang: str,
        target_lang: str,
        msgid: str,
        msgctxt: str | None = None,
        glossary_hash: str = "",
        prompt_version: str = "1.0",
    ) -> str | None:
        """Lookup cached translation. Returns translated string if hit, None otherwise."""
        if not self.enabled or not msgid.strip():
            return None

        key = compute_tm_key(
            source_lang=source_lang,
            target_lang=target_lang,
            msgid=msgid,
            msgctxt=msgctxt,
            glossary_hash=glossary_hash,
            prompt_version=prompt_version,
        )

        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT target_text FROM translation_memory WHERE hash_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row:
                return str(row["target_text"])
        return None

    def store(
        self,
        source_lang: str,
        target_lang: str,
        msgid: str,
        target_text: str,
        msgctxt: str | None = None,
        glossary_hash: str = "",
        prompt_version: str = "1.0",
        model: str | None = None,
    ) -> None:
        """Store or update a verified translation in Translation Memory."""
        if not self.enabled or not msgid.strip() or not target_text.strip():
            return

        key = compute_tm_key(
            source_lang=source_lang,
            target_lang=target_lang,
            msgid=msgid,
            msgctxt=msgctxt,
            glossary_hash=glossary_hash,
            prompt_version=prompt_version,
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO translation_memory
                    (hash_key, source_lang, target_lang, source_text, target_text, msgctxt, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hash_key) DO UPDATE SET
                    target_text = excluded.target_text,
                    model = excluded.model,
                    created_at = CURRENT_TIMESTAMP
                """,
                (key, source_lang, target_lang, msgid, target_text, msgctxt, model),
            )

    def clear(self) -> None:
        """Clear all entries in Translation Memory."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM translation_memory")
