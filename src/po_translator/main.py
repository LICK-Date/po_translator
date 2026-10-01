"""Desktop application GUI entry point."""

import sys

from PySide6.QtWidgets import QApplication

from po_translator.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PO LLM Translator")
    app.setOrganizationName("TranslateAgent")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
