"""Colours and type from the design mockups: neutral greys, colour only for small status marks."""
from PySide6.QtGui import QColor

SANS = 'Noto Sans'
MONO = 'Noto Sans Mono'  # the mockups use IBM Plex, which is not installed; Noto is the closest present

BG = '#1a1a1a'
HEADER = '#121212'
PANEL = '#1f1f1f'
STRIP = '#141414'
FOOTER = '#101010'
LINE = '#2a2a2a'
TEXT = '#e6e6e6'
DIM = '#8a8a8a'
FAINT = '#555555'
KEY_BG = '#262626'

# oklch(0.80 0.12 80) etc. from the mockups, converted to sRGB
AMBER = '#e2b45c'
RED = '#e06b5f'
GREEN = '#6fca8c'
BLUE = '#6cb1e6'


def palette():
    """Dark Fusion palette, so nothing unstyled falls back to light system colours."""
    from PySide6.QtGui import QPalette
    p = QPalette()
    for role, value in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, '#141414'),
                        (QPalette.ColorRole.AlternateBase, PANEL), (QPalette.ColorRole.Button, PANEL),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.WindowText, TEXT),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, '#4a4a4a'),
                        (QPalette.ColorRole.HighlightedText, '#ffffff'), (QPalette.ColorRole.PlaceholderText, '#6a6a6a'),
                        (QPalette.ColorRole.ToolTipBase, '#222222'), (QPalette.ColorRole.ToolTipText, TEXT)):
        p.setColor(role, QColor(value))
    return p


STYLE = f"""
* {{ font-family: '{SANS}'; color: {TEXT}; }}
QMainWindow, QWidget#page {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel[dim="true"] {{ color: {DIM}; }}
QLabel[mono="true"] {{ font-family: '{MONO}'; }}
QPushButton {{ background: transparent; border: 1px solid #3a3a3a; border-radius: 3px; padding: 6px 14px; }}
QPushButton:hover {{ background: #262626; }}
QPushButton[primary="true"] {{ background: {TEXT}; color: #111; border: none; font-weight: 500; }}
QPushButton[primary="true"]:hover {{ background: #ffffff; }}
QPushButton:checked {{ background: #4a4a4a; border-color: #4a4a4a; }}
QPushButton:disabled {{ color: {FAINT}; border-color: #2e2e2e; }}
QLineEdit, QComboBox, QPlainTextEdit {{ background: #141414; border: 1px solid #3a3a3a; border-radius: 3px;
    padding: 6px 8px; selection-background-color: #4a4a4a; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: #6a6a6a; }}
QComboBox QAbstractItemView {{ background: #1f1f1f; border: 1px solid #3a3a3a; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {FAINT}; }}
QScrollArea {{ border: none; background: transparent; }}
QDialog {{ background: #1c1c1c; }}
QToolTip {{ background: #222; color: {TEXT}; border: 1px solid #444; }}
"""
