"""Roll start and roll settings (docs/design/Roll Form.dc.html)."""
import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
                               QLineEdit, QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from .. import roll as rolls
from . import theme as t
from .i18n import tr
from .widgets import label, scoped, wrapped


def section(text):
    widget = label(text.upper(), 12, t.DIM)
    widget.setStyleSheet(f'color: {t.DIM}; border-bottom: 1px solid #2e2e2e; padding-bottom: 6px;')
    return widget


def field(name, widget, required=False):
    box = QVBoxLayout()
    box.setSpacing(6)
    box.addWidget(label(name + (' *' if required else ''), 12, '#a3a3a3'))
    box.addWidget(widget)
    return box


def segmented(options):
    """Exclusive toggle buttons; returns (layout, group) with button ids in option order."""
    row = QHBoxLayout()
    row.setSpacing(0)
    group = QButtonGroup(row)
    for i, text in enumerate(options):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setStyleSheet('border-radius: 0; padding: 8px 14px;')
        group.addButton(button, i)
        row.addWidget(button)
    group.button(0).setChecked(True)
    return row, group


class RollForm(QWidget):
    accepted = Signal(dict, dict)
    cancelled = Signal()
    open_requested = Signal(str)

    def __init__(self, mode='start', roll=None, recent=(), defaults=None):
        """mode 'start' (new roll, settings from `defaults`) or 'settings' (edit `roll`)."""
        super().__init__()
        self.setObjectName('page')
        self.mode, self.roll = mode, roll
        details = copy.deepcopy(roll.details) if roll else {'film_type': 'colour_negative'}
        settings = copy.deepcopy(roll.settings if roll else (defaults[1] if defaults else rolls.DEFAULT_SETTINGS))
        self.settings = settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)

        if mode == 'start':
            side = QWidget()
            side.setFixedWidth(340)
            scoped(side, 'side', f'background: #181818; border-right: 1px solid {t.LINE};')
            sl = QVBoxLayout(side)
            sl.setContentsMargins(24, 28, 24, 28)
            sl.setSpacing(6)
            sl.addWidget(label(tr('reopen').upper(), 12, t.DIM))
            sl.addWidget(label(str(rolls.ROOT).replace(str(rolls.ROOT.home()), '~') + '/', 11, '#6e6e6e', mono=True))
            for path, meta in recent:
                button = QPushButton(f'{path.name}\n{meta}')
                button.setStyleSheet('text-align: left; background: #1f1f1f; border: none; padding: 10px 12px;')
                button.clicked.connect(lambda _=False, p=str(path): self.open_requested.emit(p))
                sl.addWidget(button)
            other = QPushButton(tr('other_folder') + '    Ctrl+O')
            other.clicked.connect(self.choose_roll)
            sl.addWidget(other)
            sl.addStretch()
            body.addWidget(side)

        main = QVBoxLayout()
        main.setContentsMargins(36, 28, 36, 28)
        main.setSpacing(20)
        body.addLayout(main, 1)
        banner = tr('banner_settings') if mode == 'settings' else (
            tr('banner_last', name=defaults[0]) if defaults else '')
        if banner:
            b = label('i    ' + banner, 13, '#b8b8b8')
            b.setStyleSheet('color: #b8b8b8; background: #232323; border: 1px solid #303030; border-radius: 3px; padding: 10px 14px;')
            main.addWidget(b)
        columns = QHBoxLayout()
        columns.setSpacing(40)
        main.addLayout(columns)
        main.addStretch()

        left = QVBoxLayout()
        left.setSpacing(16)
        columns.addLayout(left, 1)
        left.addWidget(section(tr('details')))
        self.name = QLineEdit(details.get('name', ''))
        self.name.setReadOnly(mode == 'settings')  # shortcut: renaming a roll folder is not supported yet
        left.addLayout(field(tr('name'), self.name, True))
        types, self.film_type = segmented([tr(f) for f in rolls.FILM_TYPES])
        self.film_type.button(rolls.FILM_TYPES.index(details['film_type'])).setChecked(True)
        self.film_type.idToggled.connect(lambda *_: self.update_dng())
        left.addLayout(field(tr('film_type'), self._wrap(types), True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(16)
        self.inputs = {}
        for key in ('film_stock', 'iso', 'camera', 'lens', 'date', 'developed_by'):
            self.inputs[key] = QLineEdit(str(details.get(key, '')))
            self.inputs[key].setPlaceholderText(tr('optional'))
        self.push_pull = QComboBox()
        self.push_pull.addItems(['−2', '−1', '±0', '+1', '+2', '+3'])
        self.push_pull.setCurrentText(details.get('push_pull', '±0'))
        grid.addLayout(field(tr('film_stock'), self.inputs['film_stock']), 0, 0)
        grid.addLayout(field(tr('iso'), self.inputs['iso']), 0, 1)
        grid.addLayout(field(tr('push_pull'), self.push_pull), 0, 2)
        grid.addLayout(field(tr('camera'), self.inputs['camera']), 1, 0)
        grid.addLayout(field(tr('lens'), self.inputs['lens']), 1, 1, 1, 2)
        grid.addLayout(field(tr('date'), self.inputs['date']), 2, 0)
        grid.addLayout(field(tr('developed_by'), self.inputs['developed_by']), 2, 1, 1, 2)
        left.addLayout(grid)
        self.notes = QPlainTextEdit(details.get('notes', ''))
        self.notes.setFixedHeight(64)
        left.addLayout(field(tr('notes'), self.notes))

        right = QVBoxLayout()
        right.setSpacing(18)
        columns.addLayout(right, 1)
        right.addWidget(section(tr('per_roll')))
        looks, self.look = segmented([tr(look) for look in rolls.LOOKS])
        self.look.button(rolls.LOOKS.index(settings['look'])).setChecked(True)
        looks.addStretch()
        right.addLayout(field(tr('look'), self._wrap(looks)))
        self.multi = QCheckBox(tr('multi'))
        self.multi.setChecked(settings['multi_exposure'])
        right.addWidget(self.multi)
        right.addWidget(label(tr('multi_hint'), 12, t.DIM))
        right.addWidget(label(tr('export'), 12, '#a3a3a3'))
        export = settings['export']
        tiff = QHBoxLayout()
        self.tiff = QCheckBox('TIFF 16 Bit')
        self.tiff.setChecked(export['tiff'])
        self.tiff_space = QComboBox()
        self.tiff_space.addItems(['sRGB', 'Adobe RGB', 'ProPhoto'])
        self.tiff_space.setCurrentIndex(rolls.TIFF_SPACES.index(export['tiff_space']))
        tiff.addWidget(self.tiff)
        tiff.addWidget(self.tiff_space)
        tiff.addStretch()
        right.addLayout(tiff)
        self.jpeg = QCheckBox('JPEG  ·  sRGB')
        self.jpeg.setChecked(export['jpeg'])
        right.addWidget(self.jpeg)
        # shortcut: TIFF and JPEG are stored as settings only; they are written once development lands
        right.addWidget(label('TIFF, JPEG: ' + tr('not_yet'), 11, '#6e6e6e'))
        self.dng = QCheckBox(tr('dng'))
        self.dng.setChecked(export['dng'])
        right.addWidget(self.dng)
        dng = QHBoxLayout()
        dng.setContentsMargins(26, 0, 0, 0)
        self.dng_clean = QRadioButton(tr('dng_clean'))
        self.dng_raw = QRadioButton(tr('dng_raw'))
        (self.dng_clean if export['dng_dust_cleaned'] else self.dng_raw).setChecked(True)
        dng.addWidget(self.dng_clean)
        dng.addWidget(self.dng_raw)
        dng.addStretch()
        right.addLayout(dng)
        self.bw_note = wrapped(tr('bw_ir'), 12, '#9a9a9a')
        right.addWidget(self.bw_note)
        folder = QHBoxLayout()
        self.folder = QLineEdit(export['folder'] or '')
        self.folder.setPlaceholderText('<Rolle>/Export/')
        choose = QPushButton(tr('choose'))
        choose.clicked.connect(self.choose_folder)
        folder.addWidget(self.folder, 1)
        folder.addWidget(choose)
        right.addLayout(field(tr('export_folder'), self._wrap(folder)))
        self.update_dng()

        footer = QWidget()
        scoped(footer, 'formfooter', 'background: #181818; border-top: 1px solid #2e2e2e;')
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(36, 14, 36, 14)
        fl.addWidget(label(tr('foot_settings' if mode == 'settings' else 'foot_note'), 13, t.DIM))
        fl.addStretch()
        cancel = QPushButton(f'{tr("close" if mode == "settings" else "cancel")}    Esc')
        cancel.clicked.connect(self.cancelled)
        fl.addWidget(cancel)
        if mode == 'start':
            create = QPushButton(f'{tr("create")}    Ctrl+Enter')
            create.setProperty('primary', True)
            create.clicked.connect(self.submit)
            fl.addWidget(create)
        outer.addWidget(footer)
        self.error = label('', 13, t.RED)
        main.addWidget(self.error)

    def _wrap(self, layout):
        widget = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        return widget

    def update_dng(self):
        bw = rolls.FILM_TYPES[self.film_type.checkedId()] == 'bw_negative'
        if bw:
            self.dng_raw.setChecked(True)
        self.dng_clean.setEnabled(not bw)
        self.bw_note.setVisible(bw)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr('export_folder'), self.folder.text() or str(rolls.ROOT))
        if path:
            self.folder.setText(path)

    def choose_roll(self):
        path = QFileDialog.getExistingDirectory(self, tr('open_roll'), str(rolls.ROOT))
        if path:
            self.open_requested.emit(path)

    def values(self):
        details = {'name': self.name.text().strip(), 'film_type': rolls.FILM_TYPES[self.film_type.checkedId()]}
        for key, widget in self.inputs.items():
            if widget.text().strip():
                details[key] = widget.text().strip()
        if self.push_pull.currentText() != '±0':
            details['push_pull'] = self.push_pull.currentText()
        if self.notes.toPlainText().strip():
            details['notes'] = self.notes.toPlainText().strip()
        settings = {'look': rolls.LOOKS[self.look.checkedId()], 'multi_exposure': self.multi.isChecked(),
                    'export': {'tiff': self.tiff.isChecked(), 'tiff_space': rolls.TIFF_SPACES[self.tiff_space.currentIndex()],
                               'jpeg': self.jpeg.isChecked(), 'dng': self.dng.isChecked(),
                               'dng_dust_cleaned': self.dng_clean.isChecked(), 'folder': self.folder.text().strip() or None}}
        return details, settings

    def submit(self):
        try:
            rolls.validate_name(self.name.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accepted.emit(*self.values())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit()
        else:
            super().keyPressEvent(event)
