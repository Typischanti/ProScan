"""Developing a raw scan into a positive image with a frame's correction.

shortcut: an uncalibrated first development (film base from the brightest scan
values, per-channel auto levels) so the GUI shows positives; replace it with the
Frontier-look pipeline in the development milestone.
"""
import cv2
import numpy as np

KEYS = ('D', 'C', 'M', 'Y', 'G', 'S')
LIMITS = {'D': (-12, 12), 'C': (-12, 12), 'M': (-12, 12), 'Y': (-12, 12), 'G': (-3, 3), 'S': (0, 5)}
AUTO = {'D': 0, 'C': 0, 'M': 0, 'Y': 0, 'G': 0, 'S': 2}
KEY_STEP = .025  # one density/colour key step, in normalised output units


def reduce(raw, longest=1600):
    """A float32 copy of `raw` subsampled so its longest side is about `longest` pixels."""
    step = max(1, int(np.ceil(max(raw.shape[:2]) / longest)))
    return np.asarray(raw[::step, ::step], np.float32)


def default_crop(shape):
    """The largest centred 3:2 crop of a scan of `shape` (h, w), in fractions of the scan."""
    h, w = shape[:2]
    if w / h > 1.5:
        cw = 1.5 * h / w
        return {'x': (1 - cw) / 2, 'y': 0., 'w': cw, 'h': 1., 'angle': 0., 'free': False}
    ch = w / 1.5 / h
    return {'x': 0., 'y': (1 - ch) / 2, 'w': 1., 'h': ch, 'angle': 0., 'free': False}


def rotate(image, angle):
    """Rotate about the centre by `angle` degrees (positive = counter-clockwise), same size."""
    if not angle:
        return image
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def apply_crop(image, crop):
    h, w = image.shape[:2]
    image = rotate(image, crop['angle'])
    x0, y0 = int(round(crop['x'] * w)), int(round(crop['y'] * h))
    x1, y1 = int(round((crop['x'] + crop['w']) * w)), int(round((crop['y'] + crop['h']) * h))
    return image[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]


def develop(raw, film_type, correction=AUTO):
    """8-bit sRGB positive of float32 linear `raw` (scanner counts)."""
    x = np.maximum(raw / 65535, 1e-6)
    if film_type == 'colour_positive':
        p = x ** (1 / 2.2)
    else:
        # Density above the film base: the brightest scan values are unexposed film.
        base = np.percentile(x.reshape(-1, 3), 99.5, axis=0)
        p = np.log10(base / x)
    if film_type == 'bw_negative':
        p = np.repeat(p.mean(axis=2, keepdims=True), 3, axis=2)
    low, high = np.percentile(p.reshape(-1, 3), [.5, 99.5], axis=0)
    p = (p - low) / np.maximum(high - low, 1e-6)
    c = {**AUTO, **correction}
    p = p - KEY_STEP * c['D']
    if film_type != 'bw_negative':
        # More cyan, magenta or yellow means less of its opposite: red, green or blue.
        p = p - KEY_STEP * np.array([c['C'], c['M'], c['Y']], np.float32)
    p = .5 + (p - .5) * (1 + .15 * c['G'])
    return (np.clip(p, 0, 1) * 255 + .5).astype(np.uint8)
