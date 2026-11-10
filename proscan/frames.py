"""What developing a frame needs, shared by the screen and the exports so both show the same image."""
import numpy as np

from pathlib import Path
import json

from . import capture, develop, filmdata, flat
from .files import save_json, save_npy

PROFILES = Path.home() / '.config' / 'proscan' / 'filmprofile.json'  # learned film profiles: {film stock: [r, g, b]}

SHARPEN_SIGMA = 1.  # pixels at the raw scan's 3600 dpi
NEUTRAL_SPOT = .006  # half the side of the patch measured around a neutral spot, of the scan's longer side


def view(roll, n):
    """The frame's raw scan at screen size, with the scanner's light evened out (see flat.py).

    Kept as ansicht.npy as scanned, so it is read from the full scan only once.
    """
    path = roll.frame_dir(n) / 'ansicht.npy'
    if not path.exists():
        save_npy(path, develop.reduce(np.load(roll.frame_dir(n) / 'rohscan.npy', mmap_mode='r'), 1600))
    return flat.apply(np.load(path))


def measured_base(roll, n, image=None):
    """The film base measured on frame n itself, or None; measured once and kept in the roll."""
    frame = roll.frames[n - 1]
    # Measured again after a new calibration, since it changes the edges where the film base is measured.
    if 'film_base' not in frame or frame['film_base'].get('flat', '') != flat.stamp():
        frame['film_base'] = {'measured': develop.measure_film_base(view(roll, n) if image is None else image),
                              'from': frame.get('film_base', {}).get('from'), 'flat': flat.stamp()}
    return frame['film_base']['measured']


def film_base(roll, n, image=None):
    """(rgb, source frame, kind) of the film base frame n is developed with.

    kind: 'own' (measured on the frame), 'chosen' (another frame's, picked by
    hand), 'borrowed' (the nearest frame that shows clear film) or 'estimated'
    (no frame of the roll shows clear film). Positives have no film base.
    """
    if roll.details['film_type'] == 'colour_positive':
        return None, None, None
    chosen = roll.frames[n - 1].get('film_base', {}).get('from')
    if chosen and measured_base(roll, chosen):
        return measured_base(roll, chosen), chosen, 'chosen'
    if measured_base(roll, n, image):
        return measured_base(roll, n), n, 'own'
    # Nearest earlier frame first: it was scanned closest in time, with the same lamp and film.
    for m in [*range(n - 1, 0, -1), *range(n + 1, len(roll.frames) + 1)]:
        if measured_base(roll, m):
            return measured_base(roll, m), m, 'borrowed'
    return develop.estimate_film_base(view(roll, n) if image is None else image), None, 'estimated'


def levels(roll, n, image=None):
    """Frame n's scanner levels per channel (see develop.levels); measured once and kept in the roll."""
    frame = roll.frames[n - 1]
    if frame.get('levels', {}).get('flat', '') != flat.stamp() or 'low' not in frame.get('levels', {}):
        frame['levels'] = {**develop.levels(view(roll, n) if image is None else image), 'flat': flat.stamp()}
    return frame['levels']


def _patch(roll, n, image):
    """The scan around frame n's grey point."""
    h, w = image.shape[:2]
    x, y, r = int(roll.frames[n - 1]['neutral'][0] * w), int(roll.frames[n - 1]['neutral'][1] * h), max(2, round(NEUTRAL_SPOT * max(h, w)))
    return image[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]


def grey_stops(roll, n):
    """Stops of frame n's grey point without a film profile, for learning one; measured once and kept."""
    frame, base = roll.frames[n - 1], film_base(roll, n)[0]
    key = [frame['neutral'], [float(v) for v in base], flat.stamp()]
    if frame.get('grey_stops', {}).get('of') != key:
        stops = develop._stops(_patch(roll, n, view(roll, n)), 'colour_negative', base)
        frame['grey_stops'] = {'stops': [float(v) for v in np.median(stops.reshape(-1, 3), 0)], 'of': key}
    return frame['grey_stops']['stops']


def learned_gain(roll):
    """The film profile learned from the roll's own grey points (see develop.fit_gain), or None."""
    return develop.fit_gain([grey_stops(roll, f['number']) for f in roll.frames if f.get('neutral')])


def _stock(roll):
    return ''.join(ch for ch in roll.details.get('film_stock', '').lower() if ch.isalnum())


def _profiles():
    try:
        data = json.loads(PROFILES.read_text())
        return {k: tuple(float(x) for x in v) for k, v in data.items() if len(v) == 3}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def remember_gain(roll):
    """Keep the roll's learned film profile for later rolls of its film stock; True if it is new or changed."""
    learned = learned_gain(roll) if roll.details['film_type'] == 'colour_negative' and _stock(roll) else None
    if learned is None or _profiles().get(_stock(roll)) == learned:
        return False
    PROFILES.parent.mkdir(parents=True, exist_ok=True)
    save_json(PROFILES, {**_profiles(), _stock(roll): learned})
    return True


def gain(roll):
    """The roll's film profile (channel contrast, see develop.FILM_GAINS), or None.

    Learned from the roll's own grey points first, then from an earlier roll of the same film stock, then built in.
    """
    if roll.details['film_type'] != 'colour_negative':
        return None
    return learned_gain(roll) or _profiles().get(_stock(roll)) or develop.film_gain(roll.details.get('film_stock'))


def film_colour(roll, n):
    """Frame n's colour from the film data (see filmdata.deviation), for the roll's cast; measured once and kept."""
    frame, key = roll.frames[n - 1], filmdata.stock(roll.details.get('film_stock'))
    stored = frame.get('film_colour', {})
    if stored.get('stock') != key or stored.get('flat', '') != flat.stamp():
        image = view(roll, n)
        h, w = image.shape[:2]
        e = filmdata.exposure(image[h // 10:-h // 10:2, w // 10:-w // 10:2], film_base(roll, n, image)[0], key)
        frame['film_colour'] = {'dev': [float(v) for v in filmdata.deviation(e)], 'stock': key, 'flat': flat.stamp()}
    return frame['film_colour']['dev']


def roll_balance(roll):
    """The colour negative roll's own balance over all its frames (see develop.roll_balance), else None.

    shortcut: every new frame moves the medians a little, so earlier frames' exports drift slightly until
    re-exported; freeze the balance per roll if that ever shows.
    """
    if roll.details['film_type'] != 'colour_negative' or not roll.frames:
        return None
    numbers = range(1, len(roll.frames) + 1)
    if roll.settings['look'] == 'filmdata':
        return {'cast': [float(v) for v in np.median([film_colour(roll, m) for m in numbers], axis=0)]}
    return develop.roll_balance([levels(roll, m) for m in numbers], [film_base(roll, m)[0] for m in numbers], 'colour_negative',
                                gain(roll))


def params(roll, n, base, image=None, colour_from=None):
    """The frame's auto correction, measured on its cropped screen-size scan (rotation does not matter).

    A frame locked to another (auto_from, key U) takes that frame's auto correction, so a sequence of
    the same scene prints alike. A frame with colour_from (key L; `colour_from` tries one) takes only that
    frame's colours, with its own brightness.
    """
    frame = roll.frames[n - 1]
    source = frame.get('auto_from')
    if source and source != n and 1 <= source <= len(roll.frames):
        return params(roll, source, film_base(roll, source)[0])
    own = _own(roll, n, base, image)
    colour = colour_from or frame.get('colour_from')
    if colour and colour != n and 1 <= colour <= len(roll.frames) and roll.details['film_type'] != 'bw_negative':
        return develop.recolour(own, _own(roll, colour, film_base(roll, colour)[0]))
    return own


def _own(roll, n, base, image=None):
    """Frame n's own auto correction, with its neutral spot (key N) if one is picked."""
    frame = roll.frames[n - 1]
    image = view(roll, n) if image is None else image
    cropped = develop.apply_crop(image, frame['crop'], turn=False)
    scene = frame.get('correction', {}).get('scene', 'standard')
    film_type = roll.details['film_type']
    p = develop.analyse(cropped, film_type, base, roll.settings['look'], scene, roll_balance(roll), gain(roll),
                        roll.details.get('film_stock'))
    if frame.get('neutral') and film_type != 'bw_negative':
        p = develop.neutralise(p, _patch(roll, n, image), film_type, base)
    return p


def preview(roll, n):
    """The developed frame at screen size, cropped and turned: uint8 sRGB, as the window shows it."""
    frame = roll.frames[n - 1]
    image = view(roll, n)
    frame.setdefault('crop', develop.default_crop(image.shape))
    base = film_base(roll, n, image)[0]
    return develop.develop(develop.apply_crop(image, frame['crop']), roll.details['film_type'],
                           {**develop.AUTO, **frame.get('correction', {})}, base, roll.settings['look'], params(roll, n, base, image))


def render(roll, n):
    """The developed frame at full resolution: dust-cleaned, cropped, turned and sharpened, sRGB 0..1."""
    frame = roll.frames[n - 1]
    image = view(roll, n)
    # Frames scanned from the command line have not been corrected or cropped yet.
    frame.setdefault('crop', develop.default_crop(image.shape))
    correction = {**develop.AUTO, **frame.get('correction', {})}
    base = film_base(roll, n, image)[0]
    auto = params(roll, n, base, image)
    raw = develop.apply_crop(capture.load_raw(roll.frame_dir(n), dust_cleaned=roll.infrared), frame['crop'])
    developed = develop.render(raw, roll.details['film_type'], base, auto, correction, roll.settings['look'])
    return develop.sharpen(developed, develop.SHARPEN[correction['S']], SHARPEN_SIGMA)
