"""Settings dialog for configuring LLM API profiles and translation options."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from po_translator.domain.enums import TranslationMode
from po_translator.llm.client import OpenAICompatibleClient
from po_translator.llm.models import LLMProfile
from po_translator.translation.pipeline import TranslationConfig
from po_translator.ui.workers import ConnectionTestWorker


class SettingsDialog(QDialog):
    """Configuration modal for LLM connection and translation parameters."""

    def __init__(
        self,
        profile: LLMProfile,
        config: TranslationConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(520, 560)

        self.profile = profile
        self.config = config
        self._test_worker: ConnectionTestWorker | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        # Group 1: API Configuration
        api_group = QGroupBox("LLM API Settings (OpenAI Compatible)")
        api_layout = QFormLayout(api_group)

        self.base_url_edit = QLineEdit(self.profile.base_url)
        self.api_key_edit = QLineEdit(self.profile.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_edit = QLineEdit(self.profile.model)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(self.profile.temperature)

        self.rpm_spin = QSpinBox()
        self.rpm_spin.setRange(1, 1000)
        self.rpm_spin.setValue(self.profile.rpm or 60)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 50)
        self.concurrency_spin.setValue(self.profile.max_concurrency)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(int(self.profile.timeout_seconds))

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(self.profile.max_retries)

        api_layout.addRow("Base URL:", self.base_url_edit)
        api_layout.addRow("API Key:", self.api_key_edit)
        api_layout.addRow("Model:", self.model_edit)
        api_layout.addRow("Temperature:", self.temp_spin)
        api_layout.addRow("Rate Limit (RPM):", self.rpm_spin)
        api_layout.addRow("Max Concurrency:", self.concurrency_spin)
        api_layout.addRow("Timeout (seconds):", self.timeout_spin)
        api_layout.addRow("Max Retries:", self.retries_spin)

        # Test Connection button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        self.test_status_label = QLabel("")
        test_layout.addWidget(self.test_btn)
        test_layout.addWidget(self.test_status_label)
        api_layout.addRow("", test_layout)

        main_layout.addWidget(api_group)

        # Group 2: Translation Workflow Settings
        trans_group = QGroupBox("Translation Options")
        trans_layout = QFormLayout(trans_group)

        self.source_lang_edit = QLineEdit(self.config.source_lang)
        self.target_lang_edit = QLineEdit(self.config.target_lang)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Smart (Recommended)", TranslationMode.SMART)
        self.mode_combo.addItem("Fast", TranslationMode.FAST)
        self.mode_combo.addItem("Quality", TranslationMode.QUALITY)
        idx = self.mode_combo.findData(self.config.mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.auto_repair_check = QCheckBox("Automatically Repair Corrupted Placeholders")
        self.auto_repair_check.setChecked(self.config.auto_repair)

        trans_layout.addRow("Source Language:", self.source_lang_edit)
        trans_layout.addRow("Target Language:", self.target_lang_edit)
        trans_layout.addRow("Translation Mode:", self.mode_combo)
        trans_layout.addRow("", self.auto_repair_check)

        main_layout.addWidget(trans_group)

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)

    def _on_test_connection(self) -> None:
        """Asynchronously verify API connectivity."""
        self.test_btn.setEnabled(False)
        self.test_status_label.setText("Testing connection...")

        temp_profile = LLMProfile(
            base_url=self.base_url_edit.text().strip(),
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.text().strip(),
            timeout_seconds=float(self.timeout_spin.value()),
            max_retries=1,
        )

        client = OpenAICompatibleClient(temp_profile)
        self._test_worker = ConnectionTestWorker(client)
        self._test_worker.result_signal.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, success: bool, message: str) -> None:
        self.test_btn.setEnabled(True)
        if success:
            self.test_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.test_status_label.setText("✓ Connection successful!")
        else:
            self.test_status_label.setStyleSheet("color: red;")
            self.test_status_label.setText("✗ Failed")
            QMessageBox.warning(self, "Connection Test Failed", message)

    def _on_save(self) -> None:
        """Apply changes back to profile and config objects."""
        self.profile.base_url = self.base_url_edit.text().strip()
        self.profile.api_key = self.api_key_edit.text().strip()
        self.profile.model = self.model_edit.text().strip()
        self.profile.temperature = float(self.temp_spin.value())
        self.profile.rpm = self.rpm_spin.value()
        self.profile.max_concurrency = self.concurrency_spin.value()
        self.profile.timeout_seconds = float(self.timeout_spin.value())
        self.profile.max_retries = self.retries_spin.value()

        self.config.source_lang = self.source_lang_edit.text().strip()
        self.config.target_lang = self.target_lang_edit.text().strip()
        self.config.mode = self.mode_combo.currentData()
        self.config.auto_repair = self.auto_repair_check.isChecked()

        self.accept()
