"""The look 'filmdata' (Filmdaten): colour negatives developed from the film makers' published data.

1. Scanner to film: the scanner's three colour bands (fitted on 120 real frames, see SCANNER) see the
   film's dyes; from the scanned density above the film base follows each layer's dye density.
2. Film to camera: the stock's characteristic curves (Kodak and Fujifilm data sheets) give the light
   each layer received in the camera, in log exposure: a grey under daylight is equal in all three.
3. Camera to print: balanced like a lab printer (exposure and filtration per frame), the film is
   printed on virtual Kodak Portra Endura paper through a tungsten enlarger and viewed in daylight.

Steps 1 and 3 are spectral, so each is a lookup table over three channels (built once per film stock).
Data: proscan/data/films.json (sources and licence inside, CC BY-SA 4.0).
"""
import functools
import json
import threading
from pathlib import Path

import numpy as np

DATA = json.loads((Path(__file__).parent / 'data' / 'films.json').read_text())
W = np.asarray(DATA['wavelengths'])
LOG_E = np.asarray(DATA['log_exposure'])

# The scanner's colour bands as Gaussians (nm): fitted so that greys stay grey from shadow to highlight
# on four rolls (Gold 200, Portra 800) of the Reflecta CrystalScan 7200, an LED scanner.
# shortcut: fitted on two stocks of one scanner model; refit (scratch fit over all frames) for other scanners.
SCANNER = {'centre': (656.1, 534.6, 448.5), 'width': (44., 12.7, 4.)}

# Film stock names as typed in the roll details -> data; unknown stocks are developed as Gold 200.
STOCKS = (('portra160', 'kodak_portra_160'), ('portra400', 'kodak_portra_400'), ('portra800', 'kodak_portra_800'),
          ('ektar', 'kodak_ektar_100'), ('ultramax', 'kodak_ultramax_400'), ('gold', 'kodak_gold_200'),
          ('c200', 'fujifilm_c200'), ('400h', 'fujifilm_pro_400h'), ('xtra', 'fujifilm_xtra_400'), ('superia', 'fujifilm_xtra_400'))
DEFAULT = 'kodak_gold_200'

# The look: how far the roll's and the frame's colour are balanced away (0..1; the rest is the light
# as it was), print exposure, contrast, warmth (log exposure towards red, from blue), dye saturation.
# Tuned on real rolls towards bright, clean prints of consumer film the user likes (blue sky, fresh green, pastel
# walls, no orange tint): the film's cast goes fully, a little of the frame's own colour and warm shadows stay.
LOOK = {'cast': 1., 'balance': .6, 'target': .05, 'contrast': 1.2, 'warmth': -.02, 'saturation': 2.4, 'shadows': .25}
STOP = np.log10(2)  # log exposure per stop

NEUTRAL_BLACK = True
D_GRID = (-.15, 2.65, 49)   # scanned density above film base, per channel
E_GRID = (-3.5, 3.5, 41)    # log exposure, per layer


def stock(film_stock):
    """The data's film stock for the roll's free-text film stock."""
    name = ''.join(ch for ch in (film_stock or '').lower() if ch.isalnum())
    return next((key for word, key in STOCKS if word in name), DEFAULT)


@functools.cache
def _film(key):
    f = DATA['films'][key]
    return np.asarray(f['dye']), np.asarray(f['base']), np.asarray(f['curve'])


def _grid(lo, hi, n):
    axis = np.linspace(lo, hi, n)
    return np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1).reshape(-1, 3)


_BUILDING = threading.Lock()  # a roll opens with every frame developed at once: build each table only once


def exposure_table(key):
    """Log exposure per layer over a grid of scanned densities (n, n, n, 3); built once per film stock (about 2 s)."""
    with _BUILDING:
        return _exposure_table(key)


@functools.cache
def _exposure_table(key):
    dye, base, curve = _film(key)
    bands = np.exp(-.5 * ((W[:, None] - np.asarray(SCANNER['centre'])) / np.asarray(SCANNER['width'])) ** 2)
    weights = bands * 10 ** -base[:, None]
    weights /= weights.sum(0)
    d = _grid(*D_GRID)
    c = np.clip(np.linalg.solve(weights.T @ dye, d.T).T, -.5, 4.)  # linear start, then Newton on the spectral model
    for _ in range(6):
        t = 10 ** -(c @ dye.T)
        seen = t @ weights
        jac = np.einsum('nl,lj,lk->njk', t, weights, dye) / seen[:, :, None]
        step = np.linalg.solve(jac, (-np.log10(np.maximum(seen, 1e-12)) - d)[..., None])[..., 0]
        # Bounded: the grid's corners hold colours no film can have, where the model would run away.
        c = np.clip(c - step, -.5, 4.)
    e = np.stack([_inverse(curve[:, k], c[:, k]) for k in range(3)], -1)
    return e.reshape(D_GRID[2], D_GRID[2], D_GRID[2], 3).astype(np.float32)


def _inverse(curve, density):
    """Log exposure for a density on a characteristic curve, straight on past its ends.

    Past the ends at least the film's mid contrast, so a nearly flat toe or shoulder cannot run away.
    """
    lo, hi = 3, len(curve) - 4
    # The digitised curves dip by a hair at their ends; interpolation needs them rising.
    curve = np.maximum.accumulate(curve) + 1e-6 * np.arange(len(curve))
    e = np.interp(density, curve[lo:hi + 1], LOG_E[lo:hi + 1])
    mid = 1 / max(float(np.interp(0, LOG_E, np.gradient(curve, LOG_E))), .2)
    slope_lo = min((LOG_E[lo + 10] - LOG_E[lo]) / max(curve[lo + 10] - curve[lo], 1e-6), mid)
    slope_hi = min((LOG_E[hi] - LOG_E[hi - 10]) / max(curve[hi] - curve[hi - 10], 1e-6), mid)
    e = np.where(density < curve[lo], LOG_E[lo] + (density - curve[lo]) * slope_lo, e)
    return np.where(density > curve[hi], LOG_E[hi] + (density - curve[hi]) * slope_hi, e)


def _blackbody(kelvin):
    m = W * 1e-9
    return 1 / (m ** 5 * (np.exp(1.4388e-2 / (m * kelvin)) - 1))


XYZ_TO_SRGB = np.array([[3.2406, -1.5372, -.4986], [-.9689, 1.8758, .0415], [.0557, -.2040, 1.0570]])
BRADFORD = np.array([[.8951, .2664, -.1614], [-.7502, 1.7135, .0367], [.0389, -.0685, 1.0296]])


def print_table(key):
    """Linear sRGB of the print over a grid of the film's log exposures (n, n, n, 3)."""
    with _BUILDING:
        return _print_table(key)


@functools.cache
def _print_table(key):
    dye, base, curve = _film(key)
    paper = DATA['paper']
    p_dye, p_base, p_curve = np.asarray(paper['dye']), np.asarray(paper['base']), np.asarray(paper['curve'])
    sensitivity, cmf = np.asarray(paper['sensitivity']), np.asarray(DATA['cmf'])
    enlarger, daylight = _blackbody(3200), _blackbody(5000)

    def paper_exposure(e):
        c = np.stack([np.interp(e[:, k], LOG_E, curve[:, k]) for k in range(3)], -1)
        return np.log10((10 ** -(base + c @ dye.T) * enlarger) @ sensitivity)

    # Filtration: a grey at log exposure 0 prints the paper's own mid neutral.
    mid = np.linalg.lstsq(p_dye, np.asarray(paper['neutral']) - p_base, rcond=None)[0]
    filtration = np.array([np.interp(mid[k], p_curve[:, k], LOG_E) for k in range(3)]) - paper_exposure(np.zeros((1, 3)))[0]
    p = np.stack([np.interp(v, LOG_E, p_curve[:, k]) for k, v in enumerate((paper_exposure(_grid(*E_GRID)) + filtration).T)], -1)
    white = (daylight * 10 ** -p_base) @ cmf
    adapt = np.linalg.inv(BRADFORD) @ np.diag(BRADFORD @ [.9505, 1., 1.089] / (BRADFORD @ (white / white[1]))) @ BRADFORD
    xyz = (10 ** -(p_base + p @ p_dye.T) * daylight) @ cmf / white[1]
    rgb = np.clip(xyz @ (XYZ_TO_SRGB @ adapt).T, 0, None)
    if NEUTRAL_BLACK:
        # The paper's deepest black is a little blue (its yellow dye is the weakest); a lab print's looks neutral
        # and as deep as the paper's darkest channel.
        black = rgb.reshape(E_GRID[2], E_GRID[2], E_GRID[2], 3)[0, 0, 0]
        rgb = black.min() + (rgb - black) * (1 - black.min()) / (1 - black)
    return np.clip(rgb, 0, None).reshape(E_GRID[2], E_GRID[2], E_GRID[2], 3).astype(np.float32)


def lookup(table, grid, x):
    """Trilinear interpolation of `table` (n, n, n, 3) over the cube `grid` at points x (..., 3)."""
    lo, hi, n = grid
    f = np.clip((np.asarray(x, np.float32) - lo) * np.float32((n - 1) / (hi - lo)), 0, n - 1.001)
    i = f.astype(np.int32)
    f -= i
    flat = table.reshape(-1, 3)
    index = (i[..., 0] * n + i[..., 1]) * n + i[..., 2]
    fx, fy, fz = f[..., 0, None], f[..., 1, None], f[..., 2, None]

    def corner(dx, dy, dz):
        return flat[index + (dx * n + dy) * n + dz]
    xy = [(corner(0, 0, z) * (1 - fy) + corner(0, 1, z) * fy) * (1 - fx) + (corner(1, 0, z) * (1 - fy) + corner(1, 1, z) * fy) * fx
          for z in (0, 1)]
    return xy[0] * (1 - fz) + xy[1] * fz


def exposure(raw, base, key):
    """The light each layer received in the camera (log exposure, (h, w, 3)) for a scan and its film base."""
    d = np.log10(np.asarray(base, np.float32) / np.maximum(np.asarray(raw, np.float32), 1.))
    return lookup(exposure_table(key), D_GRID, d)


def deviation(e):
    """A frame's colour: each layer's median log exposure against the three's mean (what a lab balances)."""
    e = e.reshape(-1, 3)
    return np.median(e - e.mean(1, keepdims=True), 0)


def analyse(raw, base, key, scene, roll_cast=None):
    """The frame's auto correction: the log exposure taken off each layer (exposure and colour balance)."""
    e = exposure(raw[::2, ::2], base, key)
    cast = LOOK['cast'] * np.asarray(roll_cast if roll_cast is not None else deviation(e))
    colour = cast + LOOK['balance'] * (deviation(e) - cast)
    target = LOOK['target'] + (scene.get('target', .42) - .42)
    level = float(np.median(e.reshape(-1, 3).mean(1)))
    return {'stock': key, 'shift': [float(v) for v in colour + level - target]}


def print_frame(raw, base, params, c, scene, step, tones):
    """The print (sRGB-encoded 0..1) of a scan with its auto correction `params` and keys `c`.

    step: (D, colour, H) key steps in stops; tones: the colour keys' weights over the print tone.
    """
    d_step, colour_step, h_step = step
    e = exposure(raw, base, params['stock']) - np.asarray(params['shift'], np.float32)
    target = LOOK['target'] + (scene.get('target', .42) - .42)
    shift = -d_step * c['D'] - colour_step * np.array([c['C'], c['M'], c['Y']], np.float32)
    shift += (LOOK['warmth'] / STOP + scene.get('warmth', 0)) * np.array([.5, 0, -.5], np.float32)
    e = e + STOP * shift
    contrast = LOOK['contrast'] * scene.get('contrast', 1) * (1 + .12 * c['G'])
    e = target + contrast * (e - target)
    tone = np.clip((e.mean(-1, keepdims=True) - target + 1.2) / 2.4, 0, 1)
    if any(t.any() for t in tones):
        local = sum(w * t for w, t in zip((tone ** 2, 2 * tone * (1 - tone), (1 - tone) ** 2), tones))
        e = e - STOP * colour_step * local
    if LOOK.get('shadows'):  # warmth in the shadows only (log exposure towards red, from blue)
        e = e + LOOK['shadows'] * (1 - tone) ** 2 * np.array([.5, 0, -.5], np.float32)
    y = np.clip(lookup(print_table(params['stock']), E_GRID, e), 0, 1) ** (2 ** (-h_step * c['H']))
    return y
