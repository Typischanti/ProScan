"""The parts of the main screen, painted to match docs/design/Scan Screen.dc.html."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import develop
from . import theme as t
from .i18n import tr


def qimage(array):
    """QImage copy of a (h, w, 3) uint8 RGB array."""
    array = np.ascontiguousarray(array)
    h, w = array.shape[:2]
    return QImage(array.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def font(size, weight=QFont.Weight.Normal, mono=False):
    f = QFont(t.MONO if mono else t.SANS)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def label(text='', size=14, color=t.TEXT, mono=False, weight=QFont.Weight.Normal):
    widget = QLabel(text)
    widget.setFont(font(size, weight, mono))
    widget.setStyleSheet(f'color: {color};')
    return widget


def key_cap(text):
    widget = label(text, 11, '#d0d0d0', mono=True)
    widget.setStyleSheet('color: #d0d0d0; border: 1px solid #3a3a3a; border-radius: 3px; padding: 0 5px;')
    return widget


def scoped(widget, name, style):
    """Style only `widget` itself: an unscoped style sheet would also restyle every child."""
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    widget.setStyleSheet(f'#{name} {{ {style} }}')


def fmt(value):
    return f'+{value}' if value > 0 else f'−{-value}' if value < 0 else '0'


def fitted(image_size, rect):
    """The largest rect of `image_size`'s aspect ratio centred in `rect`."""
    w, h = image_size.width(), image_size.height()
    scale = min(rect.width() / w, rect.height() / h)
    return QRectF(rect.center().x() - w * scale / 2, rect.center().y() - h * scale / 2, w * scale, h * scale)


class Header(QWidget):
    grid_clicked = Signal()
    settings_clicked = Signal()
    language_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(60)
        scoped(self, 'header', f'background: {t.HEADER}; border-bottom: 1px solid {t.LINE};')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)
        layout.addWidget(label('PRO SCAN', 12, t.DIM, mono=True))
        names = QVBoxLayout()
        names.setSpacing(0)
        self.roll_name = label('', 14)
        self.roll_meta = label('', 12, t.DIM)
        names.addWidget(self.roll_name)
        names.addWidget(self.roll_meta)
        layout.addLayout(names, 1)
        self.step = QWidget()
        scoped(self.step, 'step', 'background: #1c1c1c; border: 1px solid #2e2e2e; border-radius: 4px;')
        self.step.setMinimumWidth(460)
        step = QHBoxLayout(self.step)
        step.setContentsMargins(18, 8, 18, 8)
        step.setSpacing(14)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.step_frame = label('', 13, t.DIM)
        self.step_text = label('', 19, '#f2f2f2', weight=QFont.Weight.Medium)
        for w in (self.dot, self.step_frame, self.step_text):
            step.addWidget(w)
        step.addStretch()
        self.bar = QProgressBar()
        self.bar.setFixedSize(140, 6)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setStyleSheet(f'QProgressBar {{ background: #2e2e2e; border: none; border-radius: 3px; }}'
                               f'QProgressBar::chunk {{ background: {t.BLUE}; border-radius: 3px; }}')
        step.addWidget(self.bar)
        layout.addWidget(self.step)
        right = QHBoxLayout()
        right.setSpacing(14)
        right.addStretch()
        self.scanner = label('', 13, '#a3a3a3')
        right.addWidget(self.scanner)
        self.grid = QPushButton()
        self.settings = QPushButton()
        self.language = QPushButton()
        self.language.setFont(font(12, mono=True))
        for button, signal in ((self.grid, self.grid_clicked), (self.settings, self.settings_clicked),
                               (self.language, self.language_clicked)):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(signal)
            right.addWidget(button)
        layout.addLayout(right, 1)

    def update_state(self, name, meta, frame_text, step_text, accent, scanner_text, scanner_color, has_roll, grid_on, language,
                     progress=None):
        self.bar.setVisible(progress is not None)
        self.bar.setValue(round((progress or 0) * 1000))
        self.roll_name.setText(name)
        self.roll_meta.setText(meta)
        self.step_frame.setText(frame_text)
        self.step_text.setText(step_text)
        self.dot.setStyleSheet(f'background: {accent}; border-radius: 5px;')
        self.scanner.setText(f'<span style="color:{scanner_color}">●</span>&nbsp; {scanner_text}')
        self.grid.setVisible(has_roll)
        self.settings.setVisible(has_roll)
        self.grid.setText(f'{tr("grid")}  G')
        self.grid.setStyleSheet(f'border-color: {"#cfcfcf" if grid_on else "#3a3a3a"};')
        self.settings.setText(tr('roll_settings'))
        self.language.setText('DE · en' if language == 'de' else 'de · EN')


class ImageView(QWidget):
    """The current frame, the preview check, or the crop mode over the full scan."""

    def __init__(self):
        super().__init__()
        self.image = None
        self.mode = 'normal'
        self.crop = None
        self.preview_title = ''
        self.preview_yes = ''
        self.preview_no = ''
        self.info = ('', '')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def show(self, image, mode='normal', crop=None, info=('', ''), preview=('', '', '')):
        self.image, self.mode, self.crop, self.info = image, mode, crop, info
        self.preview_title, self.preview_yes, self.preview_no = preview
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(t.BG))
        area = QRectF(self.rect()).adjusted(40, 30, -40, -50)
        if self.image is None:
            return
        target = fitted(self.image.size(), area)
        p.drawImage(target, self.image)
        p.setFont(font(12, mono=True))
        p.setPen(QColor('#7a7a7a'))
        below = QRectF(target.left(), target.bottom() + 8, target.width(), 20)
        metrics = p.fontMetrics()
        if metrics.horizontalAdvance(self.info[0]) + metrics.horizontalAdvance(self.info[1]) + 24 <= target.width():
            p.drawText(below, Qt.AlignmentFlag.AlignLeft, self.info[0])
            p.drawText(below, Qt.AlignmentFlag.AlignRight, self.info[1])
        else:
            # A portrait frame is too narrow for both ends: one line, centred under it.
            below = QRectF(area.left(), below.top(), area.width(), 20)
            p.drawText(below, Qt.AlignmentFlag.AlignHCenter, '  ·  '.join(x for x in self.info if x))
        if self.mode == 'preview':
            self._paint_preview(p, target)
        elif self.mode == 'crop' and self.crop:
            self._paint_crop(p, target)

    def _paint_preview(self, p, target):
        # Unmistakably not a finished frame: dashed amber border, watermark, bars with Enter / Esc.
        p.setPen(QPen(QColor(t.AMBER), 3, Qt.PenStyle.DashLine))
        p.drawRect(target)
        p.setFont(font(88, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255, 40))
        p.drawText(target, Qt.AlignmentFlag.AlignCenter, tr('preview'))
        bar = QRectF(target.left(), target.top(), target.width(), 44)
        p.fillRect(bar, QColor(18, 18, 18, 235))
        p.fillRect(QRectF(bar.left() + 18, bar.top() + 11, 96, 22), QColor(t.AMBER))
        p.setFont(font(13, QFont.Weight.DemiBold))
        p.setPen(QColor('#141414'))
        p.drawText(QRectF(bar.left() + 18, bar.top() + 11, 96, 22), Qt.AlignmentFlag.AlignCenter, tr('preview'))
        p.setFont(font(15))
        p.setPen(QColor(t.TEXT))
        p.drawText(bar.adjusted(130, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, f'{self.preview_title}    ')
        p.setFont(font(13))
        p.setPen(QColor('#9a9a9a'))
        p.drawText(bar.adjusted(130 + p.fontMetrics().horizontalAdvance(self.preview_title) * 1.25 + 24, 0, 0, 0),
                   Qt.AlignmentFlag.AlignVCenter, tr('preview_sub'))
        bottom = QRectF(target.left(), target.bottom() - 64, target.width(), 64)
        p.fillRect(bottom, QColor(18, 18, 18, 235))
        p.setFont(font(17, QFont.Weight.Medium))
        yes = QRectF(bottom.center().x() - 330, bottom.top() + 12, 300, 40)
        no = QRectF(bottom.center().x() + 16, bottom.top() + 12, 340, 40)
        p.setBrush(QColor(t.TEXT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(yes, 4, 4)
        p.setPen(QColor('#111'))
        p.drawText(yes, Qt.AlignmentFlag.AlignCenter, f'Enter    {self.preview_yes}')
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor('#4a4a4a'))
        p.drawRoundedRect(no, 4, 4)
        p.setPen(QColor(t.TEXT))
        p.drawText(no, Qt.AlignmentFlag.AlignCenter, f'Esc    {self.preview_no}')

    def _paint_crop(self, p, target):
        c = self.crop
        rect = QRectF(target.left() + c['x'] * target.width(), target.top() + c['y'] * target.height(),
                      c['w'] * target.width(), c['h'] * target.height())
        shade = QColor(12, 12, 12, 175)
        for r in (QRectF(target.left(), target.top(), target.width(), rect.top() - target.top()),
                  QRectF(target.left(), rect.bottom(), target.width(), target.bottom() - rect.bottom()),
                  QRectF(target.left(), rect.top(), rect.left() - target.left(), rect.height()),
                  QRectF(rect.right(), rect.top(), target.right() - rect.right(), rect.height())):
            p.fillRect(r, shade)
        p.setPen(QPen(QColor(230, 230, 230, 90), 1))
        for f in (1 / 3, 2 / 3):
            p.drawLine(rect.left() + f * rect.width(), rect.top(), rect.left() + f * rect.width(), rect.bottom())
            p.drawLine(rect.left(), rect.top() + f * rect.height(), rect.right(), rect.top() + f * rect.height())
        p.setPen(QPen(QColor(t.TEXT), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)
        p.setBrush(QColor(t.TEXT))
        for x in (rect.left(), rect.center().x(), rect.right()):
            for y in (rect.top(), rect.center().y(), rect.bottom()):
                if (x, y) != (rect.center().x(), rect.center().y()):
                    p.drawRect(QRectF(x - 5, y - 5, 10, 10))
        p.setFont(font(12, mono=True))
        tag = f'{"frei" if c["free"] else "3:2"}   {c["angle"]:+.1f}°'.replace('.', ',' if tr('frame') == 'Bild' else '.')
        p.fillRect(QRectF(rect.left() + 12, rect.top() + 12, 130, 22), QColor('#121212'))
        p.setPen(QColor(t.TEXT))
        p.drawText(QRectF(rect.left() + 20, rect.top() + 12, 130, 22), Qt.AlignmentFlag.AlignVCenter, tag)


class Card(QWidget):
    """A centred card for the scanner failure and the empty state."""

    def __init__(self, width=560):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        self.box = QWidget()
        self.box.setFixedWidth(width)
        self.content = QVBoxLayout(self.box)
        self.content.setSpacing(16)
        row.addWidget(self.box)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

    def clear(self):
        while self.content.count():
            item = self.content.takeAt(0)
            for w in [item.widget()] if item.widget() else [
                    item.layout().takeAt(0).widget() for _ in range(item.layout().count())] if item.layout() else []:
                if w:
                    discard(w)


def discard(widget):
    # Hide at once (deleteLater alone leaves it painted until the next event loop pass) but keep
    # its parent: Qt then owns the deletion, and Python never destroys it a second time.
    widget.hide()
    widget.deleteLater()


def wrapped(text, size=14, color=t.TEXT):
    widget = label(text, size, color)
    widget.setWordWrap(True)
    return widget


class CorrectionPanel(QWidget):
    reset_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(350)
        self.setStyleSheet(f'background: {t.PANEL};')
        self.state = None
        self.reset_rect = QRectF()

    def update_state(self, state):
        """state: frame, status, corrected, values, locked, bw, crop, export (glyph, color, text)."""
        self.state = state
        self.update()

    def mousePressEvent(self, event):
        if self.state and self.state['corrected'] and self.reset_rect.contains(event.position()):
            self.reset_clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.PANEL))
        p.setPen(QColor(t.LINE))
        p.drawLine(0, 0, 0, self.height())
        s = self.state
        if not s:
            return
        w = self.width()
        p.setFont(font(12))
        p.setPen(QColor(t.DIM))
        p.drawText(18, 26, tr('correction').upper())
        p.setFont(font(16))
        p.setPen(QColor(t.TEXT))
        p.drawText(18, 48, s['frame'])
        p.setFont(font(13))
        p.setPen(QColor(t.TEXT if s['corrected'] else t.DIM))
        p.drawText(18 + p.fontMetrics().horizontalAdvance(s['frame']) * 1.25 + 8, 48, s['status'])
        p.setFont(font(12))
        reset = QRectF(0, 14, p.fontMetrics().horizontalAdvance(tr('reset_auto')) + 40, 28)
        reset.moveRight(w - 18)
        self.reset_rect = reset
        p.setOpacity(1 if s['corrected'] else .4)
        p.setPen(QColor('#3a3a3a'))
        p.drawRoundedRect(reset, 3, 3)
        p.setFont(font(12))
        p.setPen(QColor('#c8c8c8'))
        p.drawText(reset.adjusted(9, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, tr('reset_auto'))
        p.setFont(font(12, mono=True))
        p.setPen(QColor(t.DIM))
        p.drawText(reset.adjusted(0, 0, -9, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, '0')
        p.setOpacity(1)
        p.setPen(QColor(t.LINE))
        p.drawLine(0, 62, w, 62)
        if s.get('presets'):
            return self._paint_presets(p, w, s['presets'])
        rows = [('D', tr('density'), 'Num + / −', False), ('H', tr('brightness'), 'H / Shift+H', False), ('C', tr('cyan'), 'Num 7 / 4', s['bw']),
                ('M', tr('magenta'), 'Num 8 / 5', s['bw']), ('Y', tr('yellow'), 'Num 9 / 6', s['bw']),
                ('G', tr('gradation'), 'Num 3 / 1', False), ('S', tr('sharpness'), 'Num × / ÷', False)]
        y = 72
        tone = s.get('tone')
        for key, name, keys, disabled in rows:
            if key == 'C':
                y = self._paint_tones(p, w, y, tone, s)
            if key == 'G':
                p.setPen(QColor(t.LINE))
                p.drawLine(18, y, w - 18, y)
            if key in 'CMY' and tone:
                name, key = f'{name} · {tr("tones")[tone]}', key + tone
            p.setOpacity(.35 if disabled else (.3 if s['locked'] else 1))
            p.setFont(font(22, QFont.Weight.DemiBold, mono=True))
            p.setPen(QColor('#cfcfcf'))
            p.drawText(QRectF(18, y, 36, 56), Qt.AlignmentFlag.AlignVCenter, key[0])
            p.setFont(font(12))
            p.setPen(QColor('#a3a3a3'))
            p.drawText(QRectF(64, y + 10, 180, 16), Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(font(11, mono=True))
            p.setPen(QColor('#7a7a7a'))
            p.drawText(QRectF(64, y + 10, 190, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, keys)
            value = s['values'][key]
            low, high = develop.LIMITS[key]
            cells = list(range(low, high + 1))
            cw = (190 - (len(cells) - 1)) / len(cells)
            neutral = develop.AUTO[key]
            for i, cell in enumerate(cells):
                if key == 'S':
                    on = 0 < cell <= value
                else:
                    on = value != 0 and ((value > 0 and 0 < cell <= value) or (value < 0 and value <= cell < 0))
                hh = 12 if cell == neutral else (9 if (high > 3 and cell % 4 == 0) else 6)
                color = '#8a8a8a' if cell == neutral else ('#e6e6e6' if on else '#343434')
                p.fillRect(QRectF(64 + i * (cw + 1), y + 44 - hh, cw, hh), QColor(color))
            p.setFont(font(34, QFont.Weight.Medium, mono=True))
            dash = disabled or s['locked']
            p.setPen(QColor(t.FAINT if dash else ('#ffffff' if value != neutral else t.DIM)))
            text = '—' if dash else (str(value) if key == 'S' else fmt(value))
            p.drawText(QRectF(w - 18 - 80, y, 80, 56), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
            p.setOpacity(1)
            y += 58
        if s['locked'] and s.get('locked_note', True):
            box = QRectF(18, 72 + 58 * 2.5, w - 36, 44)
            p.fillRect(box, QColor('#141414'))
            p.setPen(QColor('#3a3a3a'))
            p.drawRect(box)
            p.setFont(font(13))
            p.setPen(QColor('#c8c8c8'))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, tr('panel_locked'))
        if s['bw']:
            p.setFont(font(12))
            p.setPen(QColor(t.DIM))
            p.drawText(18, y + 12, tr('bw_note'))
            y += 22
        y += 8
        if s.get('film_base'):
            y = self._paint_film_base(p, w, y, s['film_base'])
        p.setPen(QColor(t.LINE))
        p.drawLine(0, y, w, y)
        p.setFont(font(13))
        p.setPen(QColor('#a3a3a3'))
        p.drawText(18, y + 24, tr('crop'))
        p.setFont(font(12))
        p.setPen(QColor('#c8c8c8'))
        p.drawText(QRectF(18, y + 10, w - 60, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tr('change'))
        p.setFont(font(11, mono=True))
        p.setPen(QColor('#4a4a4a'))
        p.drawRect(QRectF(w - 36, y + 11, 18, 18))
        p.setPen(QColor(t.TEXT))
        p.drawText(QRectF(w - 36, y + 11, 18, 18), Qt.AlignmentFlag.AlignCenter, 'A')
        p.setFont(font(15, mono=True))
        p.drawText(18, y + 52, s['crop'])
        y += 66
        p.setPen(QColor(t.LINE))
        p.drawLine(0, y, w, y)
        glyph, color, text = s['export']
        p.setFont(font(12, mono=True))
        p.setPen(QColor(color))
        p.drawText(18, y + 24, glyph)
        p.setFont(font(12))
        p.setPen(QColor('#a3a3a3'))
        p.drawText(36, y + 24, text)
        if s.get('pad', True):
            self._paint_pad(p, w, s['bw'])

    def _paint_presets(self, p, w, picking):
        """P: scenes, built-in and own presets, each with a thumbnail of the frame as it would look."""
        p.setFont(font(12))
        p.setPen(QColor(t.DIM))
        p.drawText(QRectF(18, 70, w - 36, 34), Qt.TextFlag.TextWordWrap, tr('presets_hint'))
        top, row = 112, 56
        items, selected = picking['items'], picking['selected']
        visible = max(1, int((self.height() - top - 8) // row))
        # Keep the selected preset in view; sections are labelled on their first visible row.
        first = max(0, min(selected - visible // 2, len(items) - visible))
        sections = {'scene': tr('scenes'), 'correction': tr('corrections'), 'own': tr('own_presets')}
        for i, (kind, _, name, detail, thumb) in enumerate(items[first:first + visible], first):
            y = top + (i - first) * row
            if i == selected:
                p.fillRect(QRectF(0, y, w, row - 2), QColor('#2a2a2a'))
                p.fillRect(QRectF(0, y, 3, row - 2), QColor('#e6e6e6'))
            box = QRectF(18, y + 5, 66, 44)
            scaled = thumb.scaled(66, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawImage(QPointF(box.center().x() - scaled.width() / 2, box.center().y() - scaled.height() / 2), scaled)
            p.setFont(font(13, QFont.Weight.DemiBold if i == selected else QFont.Weight.Normal))
            p.setPen(QColor('#f0f0f0' if i == selected else '#c8c8c8'))
            p.drawText(QRectF(96, y + 6, w - 114, 20), Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(font(11))
            p.setPen(QColor('#8a8a8a'))
            p.drawText(QRectF(96, y + 27, w - 114, 18), Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, int(w - 114)))
            if i == first or items[i - 1][0] != kind:
                p.setFont(font(10))
                p.setPen(QColor(t.DIM))
                p.drawText(QRectF(18, y - 2, w - 36, 12), Qt.AlignmentFlag.AlignRight, sections[kind].upper())

    def _paint_tones(self, p, w, y, tone, s):
        """Which tone range the colour keys act on (Num 2 cycles); a dot marks ranges with a correction."""
        p.setOpacity(.35 if s['bw'] else (.3 if s['locked'] else 1))
        names = tr('tones')
        cell = (w - 36 - 50) / 4
        for i, z in enumerate((None, *develop.TONES)):
            r = QRectF(18 + i * cell, y + 2, cell - 4, 22)
            active = z == tone
            if active:
                p.fillRect(r, QColor('#2e2e2e'))
            p.setFont(font(11, QFont.Weight.DemiBold if active else QFont.Weight.Normal))
            p.setPen(QColor('#f0f0f0' if active else '#8a8a8a'))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, names[z])
            keys = 'CMY' if z is None else [c + z for c in 'CMY']
            if not s['bw'] and not s['locked'] and any(s['values'].get(k) for k in keys):
                p.setBrush(QColor('#e6e6e6'))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(r.right() - 5, r.top() + 5), 2, 2)
                p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(font(11, mono=True))
        p.setPen(QColor('#7a7a7a'))
        p.drawText(QRectF(18, y + 2, w - 36, 22), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 'Num 2')
        p.setOpacity(1)
        return y + 28

    def _paint_film_base(self, p, w, y, fb):
        """FB block: which frame's film base this frame uses, and B to change it."""
        keys = fb['keys'] or []
        height = 62 + 20 * len(keys)
        if keys:
            p.fillRect(QRectF(0, y, w, height), QColor('#262626'))
            p.setPen(QColor('#6a6a6a'))
            p.drawRect(QRectF(0, y, w - 1, height))
        p.setPen(QColor(t.LINE))
        p.drawLine(0, y, w, y)
        badge = QRectF(18, y + 13, 24, 16)
        p.setPen(QColor('#cfcfcf'))
        p.drawRect(badge)
        p.setFont(font(10, mono=True))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, 'FB')
        p.setFont(font(14))
        p.setPen(QColor(t.TEXT))
        p.drawText(QRectF(50, y + 10, w - 120, 22), Qt.AlignmentFlag.AlignVCenter, fb['title'])
        p.setFont(font(12))
        p.setPen(QColor('#c8c8c8'))
        p.drawText(QRectF(18, y + 10, w - 60, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, fb['action'])
        p.setFont(font(11, mono=True))
        p.setPen(QColor('#4a4a4a'))
        p.drawRect(QRectF(w - 36, y + 12, 18, 18))
        p.setPen(QColor(t.TEXT))
        p.drawText(QRectF(w - 36, y + 12, 18, 18), Qt.AlignmentFlag.AlignCenter, 'B')
        p.setFont(font(12))
        p.setPen(QColor(t.DIM))
        p.drawText(QRectF(18, y + 34, w - 36, 22), Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, fb['sub'])
        for i, (text, key) in enumerate(keys):
            row = QRectF(18, y + 60 + 20 * i, w - 36, 18)
            p.setPen(QColor('#c8c8c8'))
            p.drawText(row, Qt.AlignmentFlag.AlignVCenter, text)
            p.setFont(font(11, mono=True))
            p.setPen(QColor('#e0e0e0'))
            p.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, key)
            p.setFont(font(12))
        return y + height

    def _paint_pad(self, p, w, bw):
        pad = tr('pad')
        keys = [(0, 0, 1, 1, 'Num', ''), (1, 0, 1, 1, '÷', pad['S-']), (2, 0, 1, 1, '×', pad['S+']), (3, 0, 1, 1, '−', pad['D-']),
                (0, 1, 1, 1, '7', pad['C+']), (1, 1, 1, 1, '8', pad['M+']), (2, 1, 1, 1, '9', pad['Y+']), (3, 1, 1, 2, '+', pad['D+']),
                (0, 2, 1, 1, '4', pad['C-']), (1, 2, 1, 1, '5', pad['M-']), (2, 2, 1, 1, '6', pad['Y-']),
                (0, 3, 1, 1, '1', pad['G-']), (1, 3, 1, 1, '2', pad['tone']), (2, 3, 1, 1, '3', pad['G+']), (3, 3, 1, 2, '↵', pad['scan']),
                (0, 4, 2, 1, '0', pad['auto']), (2, 4, 1, 1, ',', pad['grid'])]
        top = self.height() - 14 - 5 * 33 - 28
        p.fillRect(QRectF(0, top - 12, w, self.height() - top + 12), QColor('#1b1b1b'))
        p.setPen(QColor(t.LINE))
        p.drawLine(0, top - 12, w, top - 12)
        p.setFont(font(12))
        p.setPen(QColor(t.DIM))
        p.drawText(18, top + 6, tr('numpad').upper())
        p.setFont(font(11, mono=True))
        p.setPen(QColor('#7a7a7a'))
        p.drawText(QRectF(18, top - 6, w - 36, 16), Qt.AlignmentFlag.AlignRight, 'F1')
        top += 18
        cell = (w - 36 - 9) / 4
        for col, row, cs, rs, cap, fn in keys:
            r = QRectF(18 + col * (cell + 3), top + row * 33, cell * cs + 3 * (cs - 1), 30 * rs + 3 * (rs - 1))
            p.setOpacity(.35 if not fn or (bw and cap in '7894562') else 1)
            p.setBrush(QColor(t.KEY_BG))
            p.setPen(QColor('#333'))
            p.drawRoundedRect(r, 3, 3)
            p.setFont(font(10, mono=True))
            p.setPen(QColor('#7a7a7a'))
            p.drawText(r.adjusted(6, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, cap)
            p.setFont(font(12, mono=True))
            p.setPen(QColor('#e0e0e0'))
            p.drawText(r.adjusted(0, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, fn)
        p.setOpacity(1)
        p.setBrush(Qt.BrushStyle.NoBrush)


class Strip(QWidget):
    """The roll's frames in scanning order, with one slot for the next frame to load."""
    frame_clicked = Signal(int)
    TILE = 80

    def __init__(self):
        super().__init__()
        self.setFixedHeight(96)
        self.tiles = []
        self.first = 0

    def update_state(self, tiles):
        """tiles: dicts with n, image, state, corrected, borrowed, export glyph/color, selected."""
        self.tiles = tiles
        selected = next((i for i, tile in enumerate(tiles) if tile['selected']), len(tiles) - 1)
        visible = max(1, (self.width() - 40) // (self.TILE + 6))
        if selected < self.first:
            self.first = selected
        elif selected >= self.first + visible:
            self.first = selected - visible + 1
        self.first = max(0, min(self.first, len(tiles) - visible))
        self.update()

    def mousePressEvent(self, event):
        index = self.first + int((event.position().x() - 20) // (self.TILE + 6))
        if 0 <= index < len(self.tiles) and self.tiles[index]['state'] == 'done':
            self.frame_clicked.emit(self.tiles[index]['n'])

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.STRIP))
        p.setPen(QColor(t.LINE))
        p.drawLine(0, 0, self.width(), 0)
        if not self.tiles:
            return
        done = sum(tile['state'] == 'done' for tile in self.tiles)
        p.setFont(font(11, mono=True))
        p.setPen(QColor(t.DIM))
        p.drawText(QRectF(20, 6, self.width() - 40, 14), Qt.AlignmentFlag.AlignRight, f'{done} {tr("frames")}')
        x = 20
        for tile in self.tiles[self.first:]:
            if x + self.TILE > self.width() - 20:
                break
            r = QRectF(x, 24, self.TILE, 52)
            state = tile['state']
            if tile.get('image') is not None:
                p.drawImage(fitted(tile['image'].size(), r).intersected(r), tile['image'])
            else:
                p.fillRect(r, QColor('#222' if state == 'scanning' else '#161616'))
            p.setOpacity(.3 if tile.get('dim') else 1)
            pen = (QPen(QColor('#f0f0f0'), 2) if tile['selected'] else QPen(QColor('#f0f0f0'), 2, Qt.PenStyle.DashLine)
                   if tile.get('candidate') else QPen(QColor(t.AMBER), 2, Qt.PenStyle.DashLine)
                   if state == 'preview' else QPen(QColor(t.RED), 2) if state == 'failed' else QPen(QColor(t.BLUE), 1)
                   if state == 'scanning' else QPen(QColor('#383838'), 1, Qt.PenStyle.DashLine) if state == 'empty'
                   else QPen(QColor('#2e2e2e'), 1))
            p.setPen(pen)
            p.drawRect(r)
            progress = tile.get('progress')
            scanning = f'{round(progress * 100)} %' if progress is not None else '…'
            center = {'preview': (tr('preview')[:6] + '.', t.AMBER), 'failed': ('✕', t.RED), 'scanning': (scanning, '#c8c8c8')}.get(state)
            if center:
                p.setFont(font(11, QFont.Weight.DemiBold, mono=True))
                p.setPen(QColor(center[1]))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, center[0])
            if progress is not None and state in ('scanning', 'preview'):
                track = QRectF(r.left() + 3, r.bottom() - 7, r.width() - 6, 4)
                p.fillRect(track, QColor('#2e2e2e'))
                p.fillRect(QRectF(track.left(), track.top(), track.width() * progress, 4), QColor(t.BLUE))
            if tile.get('corrected'):
                p.fillRect(QRectF(r.left() + 2, r.top() + 2, 13, 13), QColor(t.TEXT))
                p.setFont(font(10, mono=True))
                p.setPen(QColor('#111'))
                p.drawText(QRectF(r.left() + 2, r.top() + 2, 13, 13), Qt.AlignmentFlag.AlignCenter, '±')
            if tile.get('borrowed'):
                badge = QRectF(r.right() - 20, r.top() + 2, 18, 12)
                p.fillRect(badge, QColor('#141414'))
                p.setPen(QColor('#cfcfcf'))
                p.drawRect(badge)
                p.setFont(font(9, mono=True))
                p.setPen(QColor(t.TEXT))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, 'FB')
            p.setFont(font(12, QFont.Weight.DemiBold if tile['selected'] else QFont.Weight.Normal, mono=True))
            p.setPen(QColor('#ffffff' if tile['selected'] else t.FAINT if state == 'empty' else '#a8a8a8'))
            p.drawText(QRectF(x, 78, self.TILE, 14), Qt.AlignmentFlag.AlignLeft, str(tile['n']))
            p.setPen(QColor(tile.get('export_color', t.FAINT)))
            p.drawText(QRectF(x, 78, self.TILE, 14), Qt.AlignmentFlag.AlignRight, tile.get('export', ''))
            p.setOpacity(1)
            x += self.TILE + 6


class GridView(QWidget):
    """12-up grid of frames to compare and correct side by side."""
    frame_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.tiles = []
        self.title = ''

    def update_state(self, title, tiles):
        self.title, self.tiles = title, tiles
        self.update()

    def _rects(self):
        area = QRectF(self.rect()).adjusted(24, 44, -24, -16)
        cw, ch = (area.width() - 3 * 14) / 4, (area.height() - 2 * 14) / 3
        return [QRectF(area.left() + (i % 4) * (cw + 14), area.top() + (i // 4) * (ch + 14), cw, ch - 22) for i in range(12)]

    def mousePressEvent(self, event):
        for rect, tile in zip(self._rects(), self.tiles):
            if rect.contains(event.position()):
                self.frame_clicked.emit(tile['n'])

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.BG))
        p.setFont(font(15))
        p.setPen(QColor(t.TEXT))
        p.drawText(QRectF(24, 12, self.width(), 22), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(font(12, mono=True))
        p.setPen(QColor(t.DIM))
        p.drawText(QRectF(0, 12, self.width() - 24, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, tr('grid_hint'))
        for rect, tile in zip(self._rects(), self.tiles):
            p.fillRect(rect, QColor('#141414'))
            if tile.get('image') is not None:
                p.drawImage(fitted(tile['image'].size(), rect), tile['image'])
            p.setPen(QPen(QColor('#f0f0f0'), 2) if tile['selected'] else QPen(QColor('#2e2e2e'), 1))
            p.drawRect(rect)
            below = QRectF(rect.left(), rect.bottom() + 4, rect.width(), 16)
            p.setFont(font(12, QFont.Weight.DemiBold, mono=True))
            p.setPen(QColor('#ffffff' if tile['selected'] else '#a8a8a8'))
            p.drawText(below, Qt.AlignmentFlag.AlignLeft, str(tile['n']))
            p.setFont(font(12, mono=True))
            p.setPen(QColor(t.TEXT if tile['corrected'] else '#7a7a7a'))
            p.drawText(below, Qt.AlignmentFlag.AlignHCenter, tile['values'])
            p.setPen(QColor(tile.get('export_color', t.FAINT)))
            p.drawText(below, Qt.AlignmentFlag.AlignRight, tile.get('export', ''))


class Footer(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        scoped(self, 'footer', f'background: {t.FOOTER}; border-top: 1px solid #242424;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)
        self.keys = QHBoxLayout()
        self.keys.setSpacing(20)
        layout.addLayout(self.keys)
        layout.addStretch()
        self.note = label('', 12, '#6e6e6e')
        layout.addWidget(self.note)
        self.shown = None

    def update_state(self, keys, note):
        # The note changes often (confirmations); only a language switch rebuilds the key hints.
        self.note.setText(note)
        if self.shown and self.shown[0] == keys:
            self.shown = (keys, note)
            return
        self.shown = (keys, note)
        while self.keys.count():
            discard(self.keys.takeAt(0).widget())
        for key, text in keys:
            w = QWidget()
            pair = QHBoxLayout(w)
            pair.setSpacing(6)
            pair.setContentsMargins(0, 0, 0, 0)
            pair.addWidget(key_cap(key))
            pair.addWidget(label(text, 12, t.DIM))
            self.keys.addWidget(w)


class Legend(QDialog):
    """F1: the number-pad mapping and the other keys."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('legend_title'))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(48)
        pad = QGridLayout()
        pad.setSpacing(8)
        names = tr('pad')
        for col, row, cs, rs, cap, fn in [(0, 0, 1, 1, 'Num', ''), (1, 0, 1, 1, '÷', 'S-'), (2, 0, 1, 1, '×', 'S+'), (3, 0, 1, 1, '−', 'D-'),
                                          (0, 1, 1, 1, '7', 'C+'), (1, 1, 1, 1, '8', 'M+'), (2, 1, 1, 1, '9', 'Y+'), (3, 1, 1, 2, '+', 'D+'),
                                          (0, 2, 1, 1, '4', 'C-'), (1, 2, 1, 1, '5', 'M-'), (2, 2, 1, 1, '6', 'Y-'),
                                          (0, 3, 1, 1, '1', 'G-'), (1, 3, 1, 1, '2', 'tone'), (2, 3, 1, 1, '3', 'G+'), (3, 3, 1, 2, 'Enter', 'scan'),
                                          (0, 4, 2, 1, '0', 'auto'), (2, 4, 1, 1, ',', 'grid')]:
            box = QWidget()
            box.setFixedSize(110 * cs + 8 * (cs - 1), 72 * rs + 8 * (rs - 1))
            scoped(box, 'key', 'background: #242424; border: 1px solid #363636; border-radius: 5px;')
            inner = QVBoxLayout(box)
            for w in (label(cap, 14, t.DIM, mono=True), label(names.get(fn, ''), 22, '#f0f0f0', True, QFont.Weight.DemiBold)):
                inner.addWidget(w)
            pad.addWidget(box, row, col, rs, cs)
        layout.addLayout(pad)
        keys = QGridLayout()
        keys.setVerticalSpacing(10)
        keys.setHorizontalSpacing(18)
        keys.addWidget(label(tr('other_keys').upper(), 13, t.DIM), 0, 0, 1, 2)
        for i, (key, text) in enumerate(tr('legend_keys'), 1):
            keys.addWidget(label(key, 13, '#f0f0f0', mono=True), i, 0)
            keys.addWidget(label(text, 14, '#d0d0d0'), i, 1)
        keys.setRowStretch(len(tr('legend_keys')) + 1, 1)
        layout.addLayout(keys)
