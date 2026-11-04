"""The Pro Scan desktop window (PySide6)."""
import sys


def main():
    from PySide6.QtWidgets import QApplication

    from .theme import STYLE, palette
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('Pro Scan')
    app.setDesktopFileName('proscan')
    app.setStyle('Fusion')
    app.setPalette(palette())
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
