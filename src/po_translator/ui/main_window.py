"""Main window for the PO LLM Translator desktop application."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from po_translator.domain.enums import FilterMode, FuzzyHandling, TranslationStatus
from po_translator.domain.models import PODocument
from po_translator.exceptions import POTranslatorError
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.models import LLMProfile
from po_translator.po.reader import POReader
from po_translator.po.writer import POWriter
from po_translator.services.translation_service import (
    TranslationService,
    TranslationSummary,
)
from po_translator.storage.database import DatabaseManager
from po_translator.storage.repositories import EntryRepository
from po_translator.storage.translation_memory import TranslationMemory
from po_translator.terminology.models import Glossary
from po_translator.translation.pipeline import TranslationConfig
from po_translator.ui.glossary_dialog import GlossaryDialog
from po_translator.ui.models.entry_table_model import EntryTableModel
from po_translator.ui.settings_dialog import SettingsDialog
from po_translator.ui.workers import TranslationWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window implementing PO viewer, editor, and workflow controls."""

    def __init__(self, db_path: str = "po_translator.db") -> None:
        super().__init__()
        self.setWindowTitle("PO LLM Translator")
        self.resize(1150, 720)

        # Core State
        self.document: PODocument | None = None
        self.current_file_path: Path | None = None
        self.glossary = Glossary()
        self.profile = LLMProfile()
        self.config = TranslationConfig()

        self.db = DatabaseManager(db_path)
        self.entry_repo = EntryRepository(self.db)
        self.tm = TranslationMemory(self.db)

        self._active_worker: TranslationWorker | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        self._init_menubar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Top Filter and Action Bar
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Filter:"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("All Statuses", None)
        self.status_combo.addItem("Pending", TranslationStatus.PENDING)
        self.status_combo.addItem("Translated", TranslationStatus.TRANSLATED)
        self.status_combo.addItem("Cached (TM)", TranslationStatus.CACHED)
        self.status_combo.addItem("Review Required", TranslationStatus.REVIEW_REQUIRED)
        self.status_combo.addItem("Failed", TranslationStatus.FAILED)
        self.status_combo.currentIndexChanged.connect(self._on_filter_changed)
        top_bar.addWidget(self.status_combo)

        top_bar.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search source or translation...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_edit)

        top_bar.addSpacing(20)

        self.start_btn = QPushButton("▶ Start Translation")
        self.start_btn.setStyleSheet("font-weight: bold; background-color: #2e7d32; color: white;")
        self.start_btn.clicked.connect(self._on_start_translation)
        top_bar.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("⏹ Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_translation)
        top_bar.addWidget(self.cancel_btn)

        main_layout.addLayout(top_bar)

        # 2. Main Content Splitter (Left: Table, Right: Details & Editor)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Table View
        self.table_view = QTableView()
        self.table_model = EntryTableModel()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.selectionModel().selectionChanged.connect(self._on_entry_selected)
        splitter.addWidget(self.table_view)

        # Right: Detail Panes
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Source Box
        src_group = QGroupBox("Source Text")
        src_layout = QVBoxLayout(src_group)
        self.source_view = QTextEdit()
        self.source_view.setReadOnly(True)
        src_layout.addWidget(self.source_view)
        right_layout.addWidget(src_group)

        # Translation Box
        trans_group = QGroupBox("Translation (Editable)")
        trans_layout = QVBoxLayout(trans_group)
        self.trans_edit = QTextEdit()
        trans_layout.addWidget(self.trans_edit)

        save_edit_layout = QHBoxLayout()
        save_edit_layout.addStretch()
        self.save_edit_btn = QPushButton("Apply Manual Edit")
        self.save_edit_btn.clicked.connect(self._on_save_manual_edit)
        save_edit_layout.addWidget(self.save_edit_btn)
        trans_layout.addLayout(save_edit_layout)

        right_layout.addWidget(trans_group)

        # Context & Comments Box
        ctx_group = QGroupBox("Context & Notes")
        ctx_layout = QVBoxLayout(ctx_group)
        self.context_view = QTextEdit()
        self.context_view.setReadOnly(True)
        ctx_layout.addWidget(self.context_view)
        right_layout.addWidget(ctx_group)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

        # 3. Bottom Progress and Status Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

    def _init_menubar(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")
        open_action = file_menu.addAction("&Open PO/POT File...")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file)

        save_action = file_menu.addAction("&Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save_file)

        save_as_action = file_menu.addAction("Save &As...")
        save_as_action.triggered.connect(self._on_save_as_file)

        file_menu.addSeparator()
        exit_action = file_menu.addAction("E&xit")
        exit_action.triggered.connect(self.close)

        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        glossary_action = tools_menu.addAction("&Manage Glossary...")
        glossary_action.triggered.connect(self._on_open_glossary)

        # Settings Menu
        settings_menu = menubar.addMenu("&Settings")
        settings_action = settings_menu.addAction("&Preferences...")
        settings_action.triggered.connect(self._on_open_settings)

    # File Handlers
    def _on_open_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open GNU gettext PO File",
            "",
            "PO Files (*.po *.pot);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self.document = POReader.read_file(file_path)
            self.current_file_path = Path(file_path)
            self.table_model.set_entries(self.document.entries)
            self._update_status_counts()
            self.setWindowTitle(f"PO LLM Translator - {self.current_file_path.name}")
        except (POTranslatorError, OSError) as e:
            logger.exception("Failed to open PO file")
            QMessageBox.critical(self, "Failed to Open File", f"Error reading PO file:\n{e}")

    def _on_save_file(self) -> None:
        if not self.document or not self.current_file_path:
            return
        try:
            POWriter.write_file(self.document, self.current_file_path, overwrite=True)
            self.status_label.setText(f"Saved: {self.current_file_path.name}")
            QMessageBox.information(self, "Saved", "File saved successfully.")
        except (POTranslatorError, OSError) as e:
            logger.exception("Failed to save PO file")
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")

    def _on_save_as_file(self) -> None:
        if not self.document:
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PO File As",
            str(self.current_file_path.with_name(f"{self.current_file_path.stem}.translated.po")) if self.current_file_path else "",
            "PO Files (*.po);;All Files (*)",
        )
        if not target_path:
            return
        try:
            POWriter.write_file(self.document, target_path, overwrite=True)
            self.status_label.setText(f"Saved As: {Path(target_path).name}")
            QMessageBox.information(self, "Saved", f"File saved successfully to:\n{target_path}")
        except (POTranslatorError, OSError) as e:
            logger.exception("Failed to save PO file as")
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")

    # Details and Selection
    def _on_entry_selected(self) -> None:
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        entry = self.table_model.get_entry(row)
        if not entry:
            return

        self.source_view.setPlainText(entry.msgid)
        self.trans_edit.setPlainText(entry.msgstr)

        context_lines = []
        if entry.msgctxt:
            context_lines.append(f"Context (msgctxt): {entry.msgctxt}")
        if entry.comments:
            context_lines.append(f"Comments: {'; '.join(entry.comments)}")
        if entry.extracted_comments:
            context_lines.append(f"Extracted Comments: {'; '.join(entry.extracted_comments)}")
        if entry.occurrences:
            occ_str = ", ".join(f"{f}:{l}" for f, l in entry.occurrences[:3])
            context_lines.append(f"Occurrences: {occ_str}")
        if entry.flags:
            context_lines.append(f"Flags: {', '.join(entry.flags)}")

        self.context_view.setPlainText("\n".join(context_lines))

    def _on_save_manual_edit(self) -> None:
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        new_text = self.trans_edit.toPlainText().strip()
        self.table_model.update_entry_at(row, new_text, TranslationStatus.TRANSLATED)
        self._update_status_counts()

    # Filter & Search
    def _on_filter_changed(self) -> None:
        status = self.status_combo.currentData()
        self.table_model.set_status_filter(status)

    def _on_search_changed(self, text: str) -> None:
        self.table_model.set_search_query(text)

    # Translation Workflow Controls
    def _on_start_translation(self) -> None:
        if not self.document:
            QMessageBox.warning(self, "No Document", "Please open a PO file first.")
            return

        if not self.profile.api_key:
            QMessageBox.warning(self, "API Key Required", "Please configure an API Key in Settings.")
            self._on_open_settings()
            return

        client = OpenAICompatibleClient(self.profile)
        service = TranslationService(
            client=client,
            translation_memory=self.tm,
        )

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self._active_worker = TranslationWorker(
            service=service,
            document=self.document,
            config=self.config,
            filter_mode=FilterMode.UNTRANSLATED_ONLY,
            fuzzy_handling=FuzzyHandling.SKIP,
        )
        self._active_worker.progress_signal.connect(self._on_worker_progress)
        self._active_worker.finished_signal.connect(self._on_worker_finished)
        self._active_worker.error_signal.connect(self._on_worker_error)
        self._active_worker.cancelled_signal.connect(self._on_worker_cancelled)
        self._active_worker.start()

    def _on_cancel_translation(self) -> None:
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling translation...")

    def _on_worker_progress(self, current: int, total: int) -> None:
        pct = int((current / total) * 100) if total > 0 else 100
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Translating batch {current}/{total} ({pct}%)...")
        # Trigger model refresh
        self.table_model.set_entries(self.document.entries if self.document else [])

    def _on_worker_finished(self, summary: TranslationSummary) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.table_model.set_entries(self.document.entries if self.document else [])
        self._update_status_counts()

        QMessageBox.information(
            self,
            "Translation Complete",
            f"Job Finished!\nTranslated: {summary.translated_count}\nCached: {summary.cached_count}\nFailed: {summary.failed_count}\nReview Required: {summary.review_count}",
        )

    def _on_worker_error(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Translation Error", message)

    def _on_worker_cancelled(self) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Translation cancelled by user.")
        self._update_status_counts()

    def _update_status_counts(self) -> None:
        if not self.document:
            return
        total = len(self.document.entries)
        trans = sum(1 for e in self.document.entries if e.status == TranslationStatus.TRANSLATED)
        cached = sum(1 for e in self.document.entries if e.status == TranslationStatus.CACHED)
        failed = sum(1 for e in self.document.entries if e.status == TranslationStatus.FAILED)
        rev = sum(1 for e in self.document.entries if e.status == TranslationStatus.REVIEW_REQUIRED)
        self.status_label.setText(f"Total: {total} | Translated: {trans} | Cached: {cached} | Review: {rev} | Failed: {failed}")

    # Dialog Openers
    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self.profile, self.config, self)
        dialog.exec()

    def _on_open_glossary(self) -> None:
        if not self.document:
            QMessageBox.warning(self, "No Document", "Please open a PO file before managing terms.")
            return
        dialog = GlossaryDialog(
            glossary=self.glossary,
            document=self.document,
            profile=self.profile,
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
            parent=self,
        )
        dialog.exec()
