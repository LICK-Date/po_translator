"""Glossary editor dialog for reviewing, locking, and auto-discovering terms."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from po_translator.domain.models import PODocument
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.models import LLMProfile
from po_translator.services.glossary_service import GlossaryService
from po_translator.terminology.models import Glossary, GlossaryTerm, TermOrigin
from po_translator.ui.workers import GlossaryDiscoveryWorker


class GlossaryDialog(QDialog):
    """Dialog for managing project terms, manual overrides, and LLM-assisted term mining."""

    COLUMNS: ClassVar[list[str]] = ["Source", "Target", "Category", "Freq", "Locked"]

    def __init__(
        self,
        glossary: Glossary,
        document: PODocument,
        profile: LLMProfile,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Glossary Manager")
        self.resize(750, 480)

        self.glossary = glossary
        self.document = document
        self.profile = profile
        self.source_lang = source_lang
        self.target_lang = target_lang

        self._discovery_worker: GlossaryDiscoveryWorker | None = None
        self._init_ui()
        self._populate_table()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add Term")
        self.add_btn.clicked.connect(self._on_add_term)
        self.del_btn = QPushButton("Delete Term")
        self.del_btn.clicked.connect(self._on_delete_term)
        self.toggle_lock_btn = QPushButton("Toggle Lock")
        self.toggle_lock_btn.clicked.connect(self._on_toggle_lock)
        self.auto_discover_btn = QPushButton("Auto Discover & Translate")
        self.auto_discover_btn.clicked.connect(self._on_auto_discover)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addWidget(self.toggle_lock_btn)
        btn_layout.addWidget(self.auto_discover_btn)
        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _populate_table(self) -> None:
        self.table.blockSignals(True)
        terms = self.glossary.all_terms()
        self.table.setRowCount(len(terms))

        for row, term in enumerate(terms):
            src_item = QTableWidgetItem(term.source)
            src_item.setFlags(src_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            tgt_item = QTableWidgetItem(term.target or "")
            cat_item = QTableWidgetItem(term.category or "")
            freq_item = QTableWidgetItem(str(term.frequency))
            freq_item.setFlags(freq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            locked_text = "🔒 Locked" if term.locked else "Unlocked"
            locked_item = QTableWidgetItem(locked_text)
            locked_item.setFlags(locked_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, src_item)
            self.table.setItem(row, 1, tgt_item)
            self.table.setItem(row, 2, cat_item)
            self.table.setItem(row, 3, freq_item)
            self.table.setItem(row, 4, locked_item)

        self.table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int) -> None:
        """When user modifies translation or category, lock the term automatically."""
        src_item = self.table.item(row, 0)
        tgt_item = self.table.item(row, 1)
        cat_item = self.table.item(row, 2)
        if not src_item or not tgt_item:
            return

        term = self.glossary.get(src_item.text())
        if term:
            new_target = tgt_item.text().strip()
            new_cat = cat_item.text().strip() if cat_item else term.category
            term.target = new_target or None
            term.category = new_cat or None
            term.locked = True  # Specification rule: editing automatically locks
            term.created_by = TermOrigin.USER

            # Update lock UI
            locked_item = self.table.item(row, 4)
            if locked_item:
                locked_item.setText("🔒 Locked")

    def _on_add_term(self) -> None:
        source, ok = QInputDialog.getText(self, "Add Glossary Term", "Source term:")
        if ok and source.strip():
            target, _ = QInputDialog.getText(self, "Add Glossary Term", f"Target translation for '{source}':")
            new_term = GlossaryTerm(
                id=GlossaryTerm.generate_id(source),
                source=source.strip(),
                target=target.strip() or None,
                locked=True,
                created_by=TermOrigin.USER,
            )
            self.glossary.add_term(new_term, overwrite_locked=True)
            self._populate_table()

    def _on_delete_term(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        src_item = self.table.item(row, 0)
        if src_item:
            self.glossary.remove_term(src_item.text())
            self._populate_table()

    def _on_toggle_lock(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        src_item = self.table.item(row, 0)
        if not src_item:
            return
        term = self.glossary.get(src_item.text())
        if term:
            term.locked = not term.locked
            self._populate_table()

    def _on_auto_discover(self) -> None:
        if not self.profile.api_key:
            QMessageBox.warning(self, "API Key Required", "Please configure an API Key in Settings first.")
            return

        self.auto_discover_btn.setEnabled(False)
        self.auto_discover_btn.setText("Discovering terms...")

        client = OpenAICompatibleClient(self.profile)
        service = GlossaryService()

        self._discovery_worker = GlossaryDiscoveryWorker(
            service=service,
            document=self.document,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            client=client,
            existing_glossary=self.glossary,
        )
        self._discovery_worker.finished_signal.connect(self._on_discovery_finished)
        self._discovery_worker.error_signal.connect(self._on_discovery_error)
        self._discovery_worker.start()

    def _on_discovery_finished(self, updated_glossary: Glossary) -> None:
        self.auto_discover_btn.setEnabled(True)
        self.auto_discover_btn.setText("Auto Discover & Translate")
        self.glossary = updated_glossary
        self._populate_table()
        QMessageBox.information(self, "Discovery Complete", f"Glossary now contains {len(self.glossary)} terms.")

    def _on_discovery_error(self, message: str) -> None:
        self.auto_discover_btn.setEnabled(True)
        self.auto_discover_btn.setText("Auto Discover & Translate")
        QMessageBox.critical(self, "Discovery Error", message)
