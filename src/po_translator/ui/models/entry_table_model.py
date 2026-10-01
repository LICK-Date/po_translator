"""High-performance table model for PO entries using Qt Model/View architecture."""

from __future__ import annotations

from typing import Any, ClassVar

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry


class EntryTableModel(QAbstractTableModel):
    """Memory-efficient table model capable of smoothly displaying 10,000+ entries."""

    COLUMNS: ClassVar[list[str]] = ["Status", "ID", "Context", "Source", "Translation"]

    STATUS_COLORS: ClassVar[dict[TranslationStatus, QColor]] = {
        TranslationStatus.TRANSLATED: QColor("#4caf50"),      # Green
        TranslationStatus.CACHED: QColor("#2196f3"),          # Blue
        TranslationStatus.REVIEW_REQUIRED: QColor("#ff9800"), # Orange
        TranslationStatus.FAILED: QColor("#f44336"),          # Red
        TranslationStatus.PENDING: QColor("#9e9e9e"),         # Grey
        TranslationStatus.SKIPPED: QColor("#757575"),         # Dark grey
    }

    def __init__(self, entries: list[TranslationEntry] | None = None) -> None:
        super().__init__()
        self._all_entries: list[TranslationEntry] = entries or []
        self._visible_entries: list[TranslationEntry] = list(self._all_entries)
        self._status_filter: TranslationStatus | None = None
        self._search_query: str = ""

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._visible_entries)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._visible_entries)):
            return None

        entry = self._visible_entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return entry.status.value.upper()
            elif col == 1:
                return entry.id[:8]
            elif col == 2:
                return entry.msgctxt or ""
            elif col == 3:
                # Truncate single-line preview in table
                return entry.msgid.replace("\n", "\\n")[:80]
            elif col == 4:
                return entry.msgstr.replace("\n", "\\n")[:80]

        elif role == Qt.ItemDataRole.ForegroundRole and col == 0:
            return self.STATUS_COLORS.get(entry.status, QColor("#000000"))

        return None

    def get_entry(self, row: int) -> TranslationEntry | None:
        """Return the underlying domain entry for a given row index."""
        if 0 <= row < len(self._visible_entries):
            return self._visible_entries[row]
        return None

    def set_entries(self, entries: list[TranslationEntry]) -> None:
        """Replace all entries and re-apply filters."""
        self.beginResetModel()
        self._all_entries = list(entries)
        self._apply_filters()
        self.endResetModel()

    def update_entry_at(self, row: int, translation: str, status: TranslationStatus) -> None:
        """Update an entry's translation and status and notify the view."""
        if 0 <= row < len(self._visible_entries):
            entry = self._visible_entries[row]
            entry.msgstr = translation
            entry.status = status
            left = self.index(row, 0)
            right = self.index(row, len(self.COLUMNS) - 1)
            self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole])

    def set_status_filter(self, status: TranslationStatus | None) -> None:
        self.beginResetModel()
        self._status_filter = status
        self._apply_filters()
        self.endResetModel()

    def set_search_query(self, query: str) -> None:
        self.beginResetModel()
        self._search_query = query.strip().lower()
        self._apply_filters()
        self.endResetModel()

    def _apply_filters(self) -> None:
        filtered = self._all_entries

        if self._status_filter is not None:
            filtered = [e for e in filtered if e.status == self._status_filter]

        if self._search_query:
            filtered = [
                e for e in filtered
                if self._search_query in e.msgid.lower() or self._search_query in e.msgstr.lower()
            ]

        self._visible_entries = filtered
