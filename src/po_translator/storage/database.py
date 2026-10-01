"""SQLite database management with WAL mode and schema initialization."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class DatabaseManager:
    """Manages SQLite connections, transactions, and schema migrations."""

    SCHEMA_SQL = """
    PRAGMA foreign_keys = ON;
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_file TEXT NOT NULL,
        source_language TEXT NOT NULL,
        target_language TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'smart',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS entries (
        id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        msgid TEXT NOT NULL,
        msgctxt TEXT,
        msgid_plural TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        current_translation TEXT,
        source_hash TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id, project_id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS glossary_terms (
        id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        source TEXT NOT NULL,
        target TEXT,
        category TEXT,
        description TEXT,
        locked INTEGER NOT NULL DEFAULT 0,
        frequency INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL DEFAULT 'algorithm',
        PRIMARY KEY (id, project_id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS translation_memory (
        hash_key TEXT PRIMARY KEY,
        source_lang TEXT NOT NULL,
        target_lang TEXT NOT NULL,
        source_text TEXT NOT NULL,
        target_text TEXT NOT NULL,
        msgctxt TEXT,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS translation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        model TEXT,
        source TEXT NOT NULL,
        translation TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(project_id, status);
    CREATE INDEX IF NOT EXISTS idx_tm_lookup ON translation_memory(source_lang, target_lang, source_text);
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        self._shared_conn: sqlite3.Connection | None = None

        if self._is_memory:
            # Use URI shared memory database so tables persist across operations in test session
            self._shared_conn = sqlite3.connect("file:memdb?mode=memory&cache=shared", uri=True)
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA foreign_keys = ON;")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Create or return an active SQLite connection with Row factory enabled."""
        if self._is_memory and self._shared_conn is not None:
            return self._shared_conn

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic transaction."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if not self._is_memory:
                conn.close()

    def initialize_schema(self) -> None:
        """Execute DDL statements to set up tables and indexes."""
        with self.transaction() as conn:
            conn.executescript(self.SCHEMA_SQL)
