"""Developing a raw scan into a positive image with a frame's correction.

Negatives: density above the frame's film base, converted to exposure stops,
balanced per frame (the auto correction), then printed through a sigmoid tone
curve, the way a lab scanner prints to virtual paper. Positives are already
the finished image: the faithful look keeps them as scanned.

The auto correction is measured once on the frame's screen-size scan
(`analyse`) and then applied unchanged at any size (`render`), so the screen
and every export show the same development.
"""
import cv2
import numpy as np

# Tone ranges for the colour keys: highlights, midtones, shadows; 'Ch' is cyan in the highlights.
TONES = ('h', 'm', 's')
TONE_KEYS = tuple(c + z for z in TONES for c in 'CMY')
KEYS = ('D', 'H', 'C', 'M', 'Y', 'G', 'S') + TONE_KEYS
LIMITS = {'D': (-12, 12), 'H': (-12, 12), 'C': (-12, 12), 'M': (-12, 12), 'Y': (-12, 12), 'G': (-3, 3), 'S': (0, 5),
          **{k: (-12, 12) for k in TONE_KEYS}}
# 'scene' is part of the correction, so copying, undo and the exports carry it with the keys.
AUTO = {'scene': 'standard', 'D': 0, 'H': 0, 'C': 0, 'M': 0, 'Y': 0, 'G': 0, 'S': 2, **{k: 0 for k in TONE_KEYS}}
H_STEP = 1 / 12  # midtone brightness: the print gamma changes by 2^(-H/12), black and white stay put
D_STEP = 1 / 6        # stops per density key step: ±12 steps = ±2 stops
COLOUR_STEP = 1 / 12  # stops per colour key step on its opposite channel
FILM_GAMMA = {'colour_negative': .6, 'bw_negative': .65}  # typical negative contrast (density per log exposure)

LOOKS = {
    # balance: how far the auto correction matches the channels (1 = fully neutral);
    # contrast: steepness of the print S-curve; saturation: chroma gain; warmth: stops towards red/yellow.
    'frontier': {'balance': .75, 'contrast': 4.5, 'saturation': 1.15, 'warmth': .06},
    'faithful': {'balance': .45, 'contrast': 3., 'saturation': 1., 'warmth': 0.},
}
# Scenes adjust the auto correction for a kind of picture. target: where the auto correction aims the
# median tone (.42 standard); contrast, saturation: factors on the look's; warmth: stops added to the look's.
SCENES = {
    'standard': {},
    'portrait': {'contrast': .85, 'saturation': .9, 'warmth': .04},
    'landscape': {'contrast': 1.1, 'saturation': 1.15},
    'backlit': {'target': .52, 'contrast': .9},
    'snow': {'target': .62},
    'night': {'target': .26},
    'indoor': {'warmth': -.15},  # the orange of bulb light; colour film only
}
LUMA = np.array([.2126, .7152, .0722], np.float32)


def reduce(raw, longest=1600):
    """A float32 copy of `raw` subsampled so its longest side is about `longest` pixels."""
    step = max(1, int(np.ceil(max(raw.shape[:2]) / longest)))
    return np.asarray(raw[::step, ::step], np.float32)


# --- geometry ------------------------------------------------------------------------------------

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


def apply_crop(image, crop, turn=True):
    """Straighten, crop, then turn by the frame's quarter turns (crop['turn'], degrees clockwise)."""
    h, w = image.shape[:2]
    image = rotate(image, crop['angle'])
    x0, y0 = int(round(crop['x'] * w)), int(round(crop['y'] * h))
    x1, y1 = int(round((crop['x'] + crop['w']) * w)), int(round((crop['y'] + crop['h']) * h))
    image = image[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    # The crop is defined on the scan as it lies in the holder; a portrait photo is turned afterwards.
    return np.rot90(image, -crop.get('turn', 0) // 90) if turn else image


# --- film base -----------------------------------------------------------------------------------

def measure_film_base(raw):
    """The film base (unexposed film) of a negative scan as RGB counts, or None when no clear film shows.

    The scan reaches past the frame to the left and right, onto the clear film between frames.
    """
    x = np.asarray(raw, np.float32)
    h, w, _ = x.shape
    interior = x[h // 10:-h // 10, w // 10:-w // 10].reshape(-1, 3)
    bright, brightest = np.percentile(interior, [99.5, 99.9], axis=0)
    found = []
    for strip in (x[h // 8:-h // 8, :w // 25], x[h // 8:-h // 8, -w // 25:]):
        pixels = strip.reshape(-1, 3)
        # Stray light past the film edge is far brighter than any film (measured: twice the film base);
        # never take it for film base. A frame without shadows may be clearly darker than its film base.
        pixels = pixels[np.all(pixels < 1.6 * brightest, axis=1)]
        if len(pixels) < 100:
            continue
        luma = pixels @ LUMA
        top = pixels[luma >= np.percentile(luma, 75)]
        base = np.median(top, axis=0)
        even = (top @ LUMA).std() / max(float(base @ LUMA), 1e-6) < .06
        # Unexposed film is about the clearest part of a negative. The scan's edges get a little less
        # light (measured: up to 12 % in blue), so allow some margin below the frame's brightest areas.
        if even and np.all(base >= .8 * bright) and np.all(base < 65535 * .97):
            found.append(base)
    return [float(v) for v in np.mean(found, axis=0)] if found else None


def estimate_film_base(raw):
    """A stand-in film base from the frame itself, for a roll where no frame shows clear film."""
    x = np.asarray(raw, np.float32)
    h, w, _ = x.shape
    return [float(v) for v in np.percentile(x[h // 10:-h // 10, w // 10:-w // 10].reshape(-1, 3), 99.8, axis=0)]


# --- development ---------------------------------------------------------------------------------

def _stops(raw, film_type, base):
    """Exposure in stops per channel: for negatives relative to the film base, for positives to full scale."""
    x = np.maximum(np.asarray(raw, np.float32), 1.)
    if film_type == 'colour_positive':
        return np.log2(x / 65535)
    e = np.log2(np.asarray(base, np.float32) / x) / FILM_GAMMA[film_type]
    if film_type == 'bw_negative':
        e = np.repeat(e.mean(axis=2, keepdims=True), 3, axis=2)
    return e


def analyse(raw, film_type, base, look, scene='standard'):
    """The frame's auto correction (JSON-able): per-channel black and white points in stops, and a brightness.

    `raw` is the cropped, screen-size scan. Like a print, the clearest film
    becomes black and the densest highlights almost white; `balance` decides
    how far the channels are matched (neutralising a cast), so a green lawn is
    not turned magenta. Thin negatives get lifted by `brightness`.
    """
    balance = LOOKS[look]['balance'] if film_type != 'bw_negative' else 0.
    e = _stops(raw, film_type, base).reshape(-1, 3)
    low, high = np.percentile(e, [.2, 99.8], axis=0)
    luma_low, luma_high = np.percentile(e @ LUMA, [.2, 99.8])
    black = luma_low + balance * (low - luma_low)
    white = luma_high + balance * (high - luma_high)
    white = np.maximum(white, black + 1.)  # never stretch less than one stop to full range
    u = np.clip((e - black) / (white - black), 1e-4, 1)
    median = float(np.median(u @ LUMA))
    # Gamma that would put the median at the target (0.42), applied only partly, as a lab scanner's auto density does.
    target = SCENES[scene].get('target', .42)
    brightness = float(np.clip((np.log(target) / np.log(max(median, 1e-3))) ** .7, .35, 1.6))
    return {'black': [float(v) for v in black], 'white': [float(v) for v in white], 'brightness': brightness}


def _print_curve(v, strength):
    """S-curve on 0..1 that keeps 0 and 1 in place; `strength` is its steepness."""
    a, b = 1 / (1 + np.exp(strength / 2)), 1 / (1 + np.exp(-strength / 2))
    return (1 / (1 + np.exp(-strength * (v - .5))) - a) / (b - a)


def render(raw, film_type, base, params, correction=AUTO, look='frontier'):
    """Display-ready sRGB-encoded float32 image (0..1) of `raw` with the frame's auto correction and keys."""
    c = {**AUTO, **correction}
    scene = SCENES[c['scene']]
    style = dict(LOOKS[look])
    style['contrast'] *= scene.get('contrast', 1)
    style['saturation'] *= scene.get('saturation', 1)
    style['warmth'] += scene.get('warmth', 0)
    gamma = params['brightness'] * 2 ** (-H_STEP * c['H'])
    black = np.asarray(params['black'], np.float32)
    span = np.asarray(params['white'], np.float32) - black
    e = _stops(raw, film_type, base)
    shift = np.full(3, -D_STEP * c['D'], np.float32)
    if film_type != 'bw_negative':
        # More cyan, magenta or yellow means less of its opposite: red, green or blue.
        shift -= COLOUR_STEP * np.array([c['C'], c['M'], c['Y']], np.float32)
        shift += style['warmth'] * np.array([.5, 0, -.5], np.float32)
    u = np.clip((e - black + shift) / span, 0, None)
    tones = [np.array([c[k + z] for k in 'CMY'], np.float32) for z in TONES]
    if film_type != 'bw_negative' and any(t.any() for t in tones):
        # Weights over the print tone (0 black .. 1 white) that sum to 1: the same step in all
        # three ranges equals the whole-frame key.
        tone = np.clip(np.clip(u, 0, 1) ** gamma @ LUMA, 0, 1)[..., None]
        weights = (tone ** 2, 2 * tone * (1 - tone), (1 - tone) ** 2)
        local = sum(w * t for w, t in zip(weights, tones))
        u = np.clip((e - black + shift - COLOUR_STEP * local) / span, 0, None)
    if film_type == 'colour_positive' and look == 'faithful':
        # The slide's own tones: linear scan to sRGB, only the white point and D applied.
        y = _srgb_encode(np.clip(2 ** ((u - 1) * span.mean()) * .95, 0, 1)) ** (2 ** (-H_STEP * c['H']))
    else:
        v = np.clip(u ** gamma, 0, 1.2)
        y = _print_curve(v, style['contrast'] * (1 + .12 * c['G']))
    if film_type != 'bw_negative' and style['saturation'] != 1:
        luma = (y @ LUMA)[..., None]
        y = luma + (y - luma) * style['saturation']
    return np.clip(y, 0, 1).astype(np.float32)


def sharpen(image, amount, sigma):
    """Unsharp mask on lightness only, so colour edges get no fringes."""
    if amount <= 0:
        return image
    luma = (image @ LUMA)[..., None]
    detail = luma - cv2.GaussianBlur(luma[..., 0], (0, 0), sigma)[..., None]
    return np.clip(image + amount * detail, 0, 1)


SHARPEN = (0., .25, .5, .75, 1., 1.3)  # unsharp amount per sharpness step S 0..5


def _srgb_encode(linear):
    return np.where(linear <= .0031308, 12.92 * linear, 1.055 * np.power(linear, 1 / 2.4) - .055)


def srgb_decode(encoded):
    return np.where(encoded <= .04045, encoded / 12.92, np.power((encoded + .055) / 1.055, 2.4))


def develop(raw, film_type, correction=AUTO, base=None, look='frontier', params=None):
    """8-bit sRGB positive of float32 linear `raw` (scanner counts); measures what it is not given."""
    if base is None and film_type != 'colour_positive':
        base = measure_film_base(raw) or estimate_film_base(raw)
    params = params or analyse(raw, film_type, base, look, {**AUTO, **correction}['scene'])
    return (render(raw, film_type, base, params, correction, look) * 255 + .5).astype(np.uint8)
