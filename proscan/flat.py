"""Evening out the scanner's light (flat-field) with a calibration scan of the empty film holder.

The lamp and optics may light the frame unevenly (measured on the CrystalScan 7200: within 1 % over
90 % of the frame, the outermost few percent up to 25 % darker, neutral in colour). A scan without
film shows only that unevenness; smoothed and normalised to its centre,
every scan is divided by it. It belongs to the scanner, so one calibration serves every roll.
"""
from pathlib import Path

import cv2
import numpy as np

from .files import save_npy

PATH = Path.home() / '.config' / 'proscan' / 'licht.npy'
_cache = {}


class CalibrationRejected(ValueError):
    pass


def make(raw):
    """The light field of a calibration scan: about 700 px float32 (h, w, 3), 1 at the centre. Rejects unsuitable scans."""
    step = max(1, max(raw.shape[:2]) // 700)  # about 700 px are plenty for a field this smooth
    x = np.asarray(raw[::step, ::step, :3], np.float32)
    h, w = x.shape[:2]
    if np.mean(x >= 65535 * .98) > .01:
        raise CalibrationRejected('Die Kalibrieraufnahme ist überbelichtet.')
    centre = np.median(x[h * 2 // 5:h * 3 // 5, w * 2 // 5:w * 3 // 5].reshape(-1, 3), axis=0)
    if np.any(centre < 65535 * .01):
        raise CalibrationRejected('Die Kalibrieraufnahme ist zu dunkel.')
    # Smooth enough that grain, dust and scratches don't count, fine enough for the falloff at the edges.
    field = np.dstack([cv2.GaussianBlur(cv2.medianBlur(np.ascontiguousarray(x[..., c]), 5), (0, 0), max(h, w) / 60)
                       for c in range(3)]) / centre
    # Below half the centre's light is the holder itself, not its window: left as it is, never boosted.
    lit = field.min(axis=2) >= .5
    # The holder can only show at the scan's edges; a dark area inside is a picture.
    count, labels = cv2.connectedComponents((~lit).astype(np.uint8))
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    inside = any(k not in border for k in range(1, count))
    if inside or lit.mean() < .5 or field[lit].max() > 1.25:
        raise CalibrationRejected('Die Kalibrieraufnahme ist nicht gleichmäßig: Bitte den Filmhalter leer einlegen, ohne Film.')
    field[~lit] = 1
    return field.astype(np.float32)


def save(field):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    save_npy(PATH, field)
    _cache.clear()


def stamp():
    """Which calibration is in use ('' for none), so measurements made under another one are redone."""
    try:
        return str(PATH.stat().st_mtime_ns)
    except OSError:
        return ''


def field():
    key = stamp()
    if key not in _cache:
        _cache.clear()
        _cache[key] = np.load(PATH) if key else None
    return _cache[key]


def apply(raw):
    """`raw` (h, w, 3) divided by the scanner's light field; unchanged without a calibration or for another scan size."""
    f = field()
    if f is None:
        return raw
    h, w = raw.shape[:2]
    if abs(f.shape[1] / f.shape[0] - w / h) > .02:
        return raw  # shortcut: a scan of another shape (another scanner) is not evened out; calibrate per scanner then
    return np.asarray(raw, np.float32) / cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR)
