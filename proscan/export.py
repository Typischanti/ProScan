"""Exporting a roll's frames in the formats chosen for that roll."""
import cv2
import numpy as np
import tifffile
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QColorSpace, QFont, QImage, QPainter

from . import capture, develop, dng, frames
from .files import atomic

# Linear sRGB -> linear target primaries (ProPhoto with Bradford adaptation D65 -> D50).
SPACES = {
    'srgb': (np.eye(3), QColorSpace.NamedColorSpace.SRgb),
    'adobe_rgb': (np.array([[.7151627, .2848373, 0.], [0., 1., 0.], [0., .0411705, .9588295]]), QColorSpace.NamedColorSpace.AdobeRgb),
    'prophoto': (np.array([[.5293459, .3300271, .1406270], [.0983723, .8734360, .0281917], [.0168810, .1176712, .8654478]]),
                 QColorSpace.NamedColorSpace.ProPhotoRgb),
}


def icc(space):
    return bytes(QColorSpace(SPACES[space][1]).iccProfile())


def encode(linear, space):
    """Apply the target space's tone response to linear values 0..1."""
    if space == 'srgb':
        return develop._srgb_encode(linear)
    if space == 'adobe_rgb':
        return np.power(linear, 256 / 563)
    return np.where(linear < 1 / 512, 16 * linear, np.power(linear, 1 / 1.8))  # ProPhoto (ROMM)


def convert(image, space):
    """sRGB-encoded 0..1 -> `space`-encoded 0..1; the development's output is defined in sRGB."""
    if space == 'srgb':
        return image
    linear = develop.srgb_decode(image) @ SPACES[space][0].T.astype(np.float32)
    return encode(np.clip(linear, 0, 1), space)


def file_stem(roll, number):
    return f'{roll.details["name"]}_{number:02d}'


def formats(roll):
    export = roll.settings['export']
    return [name for name, on in (('TIFF', export['tiff']), ('JPEG', export['jpeg']), ('DNG', export['dng'])) if on]


def write_tiff(path, image, space, xmp):
    data = np.round(convert(image, space) * 65535).astype(np.uint16)
    profile = icc(space)
    with atomic(path) as temporary:
        tifffile.imwrite(temporary, data, photometric='rgb', compression='zlib', predictor=True, software='Pro Scan',
                         metadata=None, extratags=[(34675, 'B', len(profile), profile, True), (700, 'B', len(xmp), xmp, True)])


def write_jpeg(path, image, xmp):
    ok, data = cv2.imencode('.jpg', np.round(image[..., ::-1] * 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError('JPEG konnte nicht erzeugt werden.')

    def segment(marker, payload):
        return b'\xff' + bytes([marker]) + (len(payload) + 2).to_bytes(2, 'big') + payload
    # APP1 carries the roll details (XMP), APP2 the sRGB profile; both right after the start marker.
    extra = segment(0xE1, b'http://ns.adobe.com/xap/1.0/\x00' + xmp) + segment(0xE2, b'ICC_PROFILE\x00\x01\x01' + icc('srgb'))
    with atomic(path) as temporary:
        temporary.write_bytes(data[:2].tobytes() + extra + data[2:].tobytes())


SHEET_COLUMNS, SHEET_TILE = 6, 420  # like a 35 mm strip of six; square boxes fit upright and lying frames alike


def contact_sheet(roll):
    """One JPEG of the whole roll in the export folder, as developed now; returns its path."""
    count = len(roll.frames)
    tile_w = tile_h = SHEET_TILE
    gap, label, head = 24, 30, 110
    rows = max(1, -(-count // SHEET_COLUMNS))
    width = SHEET_COLUMNS * (tile_w + gap) + gap
    sheet = np.full((head + rows * (tile_h + label + gap) + gap, width, 3), 20, np.uint8)
    places = []
    for i in range(count):
        image = frames.preview(roll, i + 1)
        scale = min(tile_w / image.shape[1], tile_h / image.shape[0])
        image = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        x = gap + i % SHEET_COLUMNS * (tile_w + gap)
        y = head + i // SHEET_COLUMNS * (tile_h + label + gap)
        oy, ox = (tile_h - image.shape[0]) // 2, (tile_w - image.shape[1]) // 2
        sheet[y + oy:y + oy + image.shape[0], x + ox:x + ox + image.shape[1]] = image
        places.append((x, y + tile_h))
    # Text with Qt: OpenCV fonts have no umlauts.
    canvas = QImage(sheet.data, width, sheet.shape[0], 3 * width, QImage.Format.Format_RGB888).copy()
    p = QPainter(canvas)
    p.setPen(QColor(235, 235, 235))
    p.setFont(QFont('Noto Sans', 34))
    p.drawText(QRectF(gap, 18, width - 2 * gap, 50), Qt.AlignmentFlag.AlignVCenter, roll.details['name'])
    d = roll.details
    p.setPen(QColor(160, 160, 160))
    p.setFont(QFont('Noto Sans', 16))
    line = ' · '.join(str(x) for x in (d.get('film_stock'), d.get('iso') and f'ISO {d["iso"]}', d.get('camera'), d.get('date')) if x)
    p.drawText(QRectF(gap, 66, width - 2 * gap, 30), Qt.AlignmentFlag.AlignVCenter, line)
    p.setFont(QFont('Noto Sans Mono', 15))
    for i, (x, y) in enumerate(places):
        p.drawText(QRectF(x, y + 2, tile_w, label), Qt.AlignmentFlag.AlignCenter, str(i + 1))
    p.end()
    ptr = canvas.constBits()
    sheet = np.frombuffer(ptr, np.uint8).reshape(canvas.height(), canvas.bytesPerLine())[:, :3 * width].reshape(canvas.height(), width, 3)
    folder = roll.export_folder
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{roll.details["name"]}_Kontaktbogen.jpg'
    write_jpeg(path, sheet / 255, dng.xmp(roll.details, None))
    return path


def export_frame(roll, number):
    """Write the frame's exports; returns the written paths."""
    export = roll.settings['export']
    folder = roll.export_folder
    folder.mkdir(parents=True, exist_ok=True)
    frame = roll.frames[number - 1]
    xmp = dng.xmp(roll.details, number)
    written = []
    if export['tiff'] or export['jpeg']:
        image = frames.render(roll, number)
        if export['tiff']:
            written.append(folder / (file_stem(roll, number) + '.tif'))
            write_tiff(written[-1], image, export['tiff_space'], xmp)
        if export['jpeg']:
            written.append(folder / (file_stem(roll, number) + '.jpg'))
            write_jpeg(written[-1], image, xmp)
    if export['dng']:
        written.append(folder / (file_stem(roll, number) + '.dng'))
        raw = capture.load_raw(roll.frame_dir(number), export['dng_dust_cleaned'])
        dng.write(written[-1], raw, roll.details, number, frame.get('crop', {}).get('turn', 0),
                  frame.get('scanner', 'Reflecta CrystalScan 7200'))
    return written
