"""Unit tests for UI EntryTableModel with offscreen Qt setup."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from po_translator.domain.enums import TranslationStatus
from po_translator.domain.models import TranslationEntry
from po_translator.ui.models.entry_table_model import EntryTableModel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestEntryTableModel:
    def test_model_row_and_column_counts(self, qapp):
        entries = [
            TranslationEntry(id="1", msgid="Start", msgstr="开始", status=TranslationStatus.TRANSLATED),
            TranslationEntry(id="2", msgid="Exit", status=TranslationStatus.PENDING),
        ]
        model = EntryTableModel(entries)

        assert model.rowCount() == 2
        assert model.columnCount() == 5
        assert model.headerData(0, Qt.Orientation.Horizontal) == "Status"
        assert model.headerData(3, Qt.Orientation.Horizontal) == "Source"

    def test_model_data_roles(self, qapp):
        entries = [
            TranslationEntry(id="1234567890", msgid="Hello World", msgstr="你好世界", status=TranslationStatus.TRANSLATED),
        ]
        model = EntryTableModel(entries)

        idx_status = model.index(0, 0)
        idx_id = model.index(0, 1)
        idx_src = model.index(0, 3)
        idx_trans = model.index(0, 4)

        assert model.data(idx_status, Qt.ItemDataRole.DisplayRole) == "TRANSLATED"
        assert model.data(idx_id, Qt.ItemDataRole.DisplayRole) == "12345678"
        assert model.data(idx_src, Qt.ItemDataRole.DisplayRole) == "Hello World"
        assert model.data(idx_trans, Qt.ItemDataRole.DisplayRole) == "你好世界"

        # Color foreground
        color = model.data(idx_status, Qt.ItemDataRole.ForegroundRole)
        assert color is not None

    def test_model_status_and_search_filters(self, qapp):
        entries = [
            TranslationEntry(id="1", msgid="Start Game", status=TranslationStatus.PENDING),
            TranslationEntry(id="2", msgid="Options", status=TranslationStatus.TRANSLATED, msgstr="选项"),
            TranslationEntry(id="3", msgid="Exit Game", status=TranslationStatus.PENDING),
        ]
        model = EntryTableModel(entries)
        assert model.rowCount() == 3

        # Filter by status: PENDING
        model.set_status_filter(TranslationStatus.PENDING)
        assert model.rowCount() == 2
        assert model.get_entry(0).msgid == "Start Game"
        assert model.get_entry(1).msgid == "Exit Game"

        # Search query: "Start"
        model.set_search_query("Start")
        assert model.rowCount() == 1
        assert model.get_entry(0).msgid == "Start Game"

        # Clear filters
        model.set_status_filter(None)
        model.set_search_query("")
        assert model.rowCount() == 3

    def test_update_entry_at(self, qapp):
        entries = [
            TranslationEntry(id="1", msgid="Save", status=TranslationStatus.PENDING),
        ]
        model = EntryTableModel(entries)

        model.update_entry_at(0, "保存", TranslationStatus.TRANSLATED)
        idx_trans = model.index(0, 4)
        idx_status = model.index(0, 0)

        assert model.data(idx_trans, Qt.ItemDataRole.DisplayRole) == "保存"
        assert model.data(idx_status, Qt.ItemDataRole.DisplayRole) == "TRANSLATED"


def test_main_window_offscreen(qapp):
    from pathlib import Path

    from po_translator.domain.models import PODocument
    from po_translator.ui.main_window import MainWindow

    window = MainWindow()
    assert "PO LLM Translator" in window.windowTitle()

    doc = PODocument(
        path=Path("dummy.po"),
        entries=[
            TranslationEntry(id="1", msgid="Game Over", msgstr="游戏结束", status=TranslationStatus.TRANSLATED),
        ],
    )
    window.document = doc
    window.table_model.set_entries(doc.entries)
    window._update_status_counts()

    assert "Total: 1" in window.status_label.text()
    assert "Translated: 1" in window.status_label.text()
    window.close()


def test_settings_dialog_offscreen(qapp):
    from po_translator.llm.models import LLMProfile
    from po_translator.translation.pipeline import TranslationConfig
    from po_translator.ui.settings_dialog import SettingsDialog

    profile = LLMProfile(base_url="https://api.openai.com/v1", api_key="")
    config = TranslationConfig(source_lang="en", target_lang="zh-CN")

    dialog = SettingsDialog(profile, config)
    dialog.base_url_edit.setText("http://localhost:8000/v1")
    dialog.api_key_edit.setText("test-key-12345")
    dialog.model_edit.setText("custom-model")
    dialog._on_save()

    assert profile.base_url == "http://localhost:8000/v1"
    assert profile.api_key == "test-key-12345"
    assert profile.model == "custom-model"
    dialog.close()


def test_glossary_dialog_offscreen(qapp):
    from pathlib import Path

    from po_translator.domain.models import PODocument
    from po_translator.llm.models import LLMProfile
    from po_translator.terminology.models import Glossary, GlossaryTerm
    from po_translator.ui.glossary_dialog import GlossaryDialog

    glossary = Glossary()
    glossary.add_term(GlossaryTerm(id="term-1", source="Potion", target="药水", locked=True))
    doc = PODocument(path=Path("dummy.po"), entries=[])
    profile = LLMProfile()

    dialog = GlossaryDialog(glossary=glossary, document=doc, profile=profile)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "Potion"
    assert dialog.table.item(0, 1).text() == "药水"
    dialog.close()
