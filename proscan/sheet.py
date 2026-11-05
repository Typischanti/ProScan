"""Contact sheets of a roll, as designed in Claude Design (canvas "Kontaktbogen"): one JPEG per sheet.

paper: variant A, a light print with the roll details above a grid of six columns.
film:  variant B, black 35 mm strips of six frames with sprocket holes and edge print.
All sizes are output pixels from the design's boards.
"""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTransform

from . import dng, frames
from .export import write_jpeg

WORDS = {'frames': '{n} Bilder', 'title': 'Kontaktbogen', 'film_type': 'Filmtyp', 'film_stock': 'Film', 'iso': 'ISO',
         'camera': 'Kamera', 'lens': 'Objektiv', 'date': 'Datum', 'developed_by': 'Entwickelt von',
         'colour_negative': 'Farbnegativ', 'bw_negative': 'Schwarzweißnegativ', 'colour_positive': 'Farbpositiv'}
FILES = {'paper': '{name}_Kontaktbogen.jpg', 'film': '{name}_Kontaktbogen_Film.jpg'}


def _font(size, weight=QFont.Weight.Normal, mono=False, tracking=0.):
    f = QFont('Noto Sans Mono' if mono else 'Noto Sans')
    f.setPixelSize(size)
    f.setWeight(weight)
    if tracking:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking * size)
    return f


def _text(p, x, y, line, text, font, colour, right=False):
    """Text whose line box has its top-left (or top-right, with `right`) corner at x, y."""
    p.setFont(font)
    p.setPen(QColor(colour))
    width = p.fontMetrics().horizontalAdvance(text) + 2
    p.drawText(QRectF(x - width if right else x, y, width, line), Qt.AlignmentFlag.AlignVCenter, text)
    return width


def _qimage(image):
    h, w = image.shape[:2]
    return QImage(np.ascontiguousarray(image).data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def _fit(w, h, box_w, box_h):
    s = min(box_w / w, box_h / h)
    return round(w * s), round(h * s)


def _iso(d):
    return ' · '.join(str(x) for x in (d.get('iso'), d.get('push_pull')) if x)


def paper(roll, images, words):
    M, COLS, W, G, AREA, LBL_GAP, LBL_H, ROW_GAP = 120, 6, 400, 40, 600, 14, 32, 50
    PITCH, WIDTH = AREA + LBL_GAP + LBL_H + ROW_GAP, 2840
    d = roll.details
    fields = [(words[k], v) for k, v in (('film_type', words.get(d['film_type'], d['film_type'])), ('film_stock', d.get('film_stock')),
                                         ('iso', _iso(d)), ('camera', d.get('camera')), ('lens', d.get('lens')),
                                         ('date', d.get('date')), ('developed_by', d.get('developed_by'))) if v]
    # Lay out the field row first (it wraps past 2600), since the rule and the grid follow it.
    probe = QImage(1, 1, QImage.Format.Format_RGB888)
    p = QPainter(probe)
    placed, x, y = [], M, 244
    for label, value in fields:
        p.setFont(_font(20, QFont.Weight.DemiBold, tracking=.12))
        lw = p.fontMetrics().horizontalAdvance(label.upper())
        p.setFont(_font(34))
        w = max(lw, p.fontMetrics().horizontalAdvance(str(value)))
        if x > M and x + w > M + 2600:
            x, y = M, y + 74 + 24
        placed.append((x, y, label, str(value)))
        x += w + 72
    p.end()
    rule = (y + 114) if fields else 256  # 358 for one field row
    top = rule + 3 + 64
    cells, col, row = [], 0, 0
    for image in images:
        lying = image.shape[1] > image.shape[0]
        span = 2 if lying else 1
        if col + span > COLS:
            col, row = 0, row + 1
        box_w, box_h = (2 * W + G, 560) if lying else (W, AREA)
        w, h = _fit(image.shape[1], image.shape[0], box_w, box_h)
        x0 = M + col * (W + G) + (box_w - w) // 2
        cells.append((image, x0, top + row * PITCH + AREA - h, w, h, M + col * (W + G), top + row * PITCH + AREA + LBL_GAP))
        col += span
        if col >= COLS:
            col, row = 0, row + 1
    rows = row + (col > 0)
    foot = top + rows * PITCH - ROW_GAP + 64
    canvas = QImage(WIDTH, foot + 21 + 28 + M, QImage.Format.Format_RGB888)
    canvas.fill(QColor('#FBFAF7'))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    count = words['frames'].format(n=len(images))
    p.setFont(_font(26, mono=True))
    name_w = 2600 - p.fontMetrics().horizontalAdvance(count) - 48
    p.setFont(_font(84, QFont.Weight.DemiBold, tracking=-.01))
    name = p.fontMetrics().elidedText(d['name'], Qt.TextElideMode.ElideRight, name_w)
    _text(p, M, 120, 96, name, _font(84, QFont.Weight.DemiBold, tracking=-.01), '#1C1B19')
    _text(p, M + 2600, 184, 32, count, _font(26, mono=True), '#5F5A52', right=True)
    for x, y, label, value in placed:
        _text(p, x, y, 24, label.upper(), _font(20, QFont.Weight.DemiBold, tracking=.12), '#77716A')
        _text(p, x, y + 30, 44, value, _font(34), '#1C1B19')
    p.fillRect(QRectF(M, rule, 2600, 3), QColor('#1C1B19'))
    for i, (image, x, y, w, h, lx, ly) in enumerate(cells):
        p.drawImage(QRectF(x, y, w, h), _qimage(image))
        _text(p, lx, ly, 32, str(i + 1), _font(26, QFont.Weight.Medium, mono=True), '#5F5A52')
    p.fillRect(QRectF(M, foot, 2600, 1), QColor('#D6D0C4'))
    _text(p, M, foot + 21, 28, f'{d["name"]} · {words["title"]}', _font(22), '#77716A')
    _text(p, M + 2600, foot + 21, 28, 'Pro Scan', _font(22), '#77716A', right=True)
    p.end()
    return canvas


def film(roll, images, words):
    PER, PW, PH, FG, PAD, SH, SG, TOP, HOLE, PAPER = 6, 480, 320, 24, 24, 504, 40, 340, 63, '#F2EFE8'
    d = roll.details
    strips = -(-len(images) // PER)
    foot = TOP + strips * (SH + SG) - SG + 56
    canvas = QImage(3288, foot + 28 + 120, QImage.Format.Format_RGB888)
    canvas.fill(QColor(PAPER))
    p = QPainter(canvas)
    p.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
    _text(p, 120, 120, 96, d['name'], _font(84, QFont.Weight.Bold, tracking=-.01), '#161514')
    line = ' · '.join(x for x in (d.get('film_stock'), d.get('iso') and f'ISO {_iso(d)}', d.get('camera'), d.get('lens'),
                                   d.get('date')) if x)
    _text(p, 120, 232, 36, line.upper(), _font(28, QFont.Weight.Medium, mono=True, tracking=.04), '#5E5950')
    edge = (d.get('film_stock') or '').upper()
    for s in range(strips):
        chunk = images[s * PER:(s + 1) * PER]
        sx, sy, sw = 120, TOP + s * (SH + SG), len(chunk) * (PW + FG) + PAD
        p.fillRect(QRectF(sx, sy, sw, SH), QColor('#161514'))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PAPER))
        hx = 18
        while hx + 24 <= sw - 10:
            for hy in (14, 456):
                p.drawRoundedRect(QRectF(sx + hx, sy + hy, 24, 34), 4, 4)
            hx += HOLE
        p.setBrush(Qt.BrushStyle.NoBrush)
        for j, image in enumerate(chunk):
            x = sx + PAD + j * (PW + FG)
            p.fillRect(QRectF(x, sy + 92, PW, PH), QColor('#000000'))
            picture = _qimage(image)
            if image.shape[0] > image.shape[1]:
                # Upright frames lie on their side as on the film: turned 90° to the left.
                picture = picture.transformed(QTransform().rotate(-90))
            w, h = _fit(picture.width(), picture.height(), PW, PH)
            p.drawImage(QRectF(x + (PW - w) / 2, sy + 92 + (PH - h) / 2, w, h), picture)
            if edge and j % 2 == 0:
                _text(p, x + 8, sy + 60, 20, edge, _font(16, QFont.Weight.DemiBold, mono=True, tracking=.2), '#C98F33')
            _text(p, x + 8, sy + 418, 32, str(s * PER + j + 1), _font(28, QFont.Weight.Bold, mono=True), '#F0B44C')
    _text(p, 120, foot, 28, f'{words["frames"].format(n=len(images))} · Pro Scan {words["title"]}', _font(22, mono=True), '#6E685F')
    p.end()
    return canvas


def contact_sheet(roll, style='paper', words=None):
    """Write the roll's contact sheet in `style` ('paper' or 'film') to its export folder; returns the path.

    words: the sheet's labels (see WORDS) in the app's language.
    """
    words = {**WORDS, **(words or {})}
    images = [frames.preview(roll, n) for n in range(1, len(roll.frames) + 1)]
    canvas = {'paper': paper, 'film': film}[style](roll, images, words)
    data = np.frombuffer(canvas.constBits(), np.uint8).reshape(canvas.height(), canvas.bytesPerLine())
    sheet = data[:, :3 * canvas.width()].reshape(canvas.height(), canvas.width(), 3)
    folder = roll.export_folder
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILES[style].format(name=roll.details['name'])
    write_jpeg(path, sheet / 255, dng.xmp(roll.details, None))
    return path
