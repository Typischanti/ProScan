"""What developing a frame needs, shared by the screen and the exports so both show the same image."""
import numpy as np

from . import capture, develop
from .files import save_npy

SHARPEN_SIGMA = 1.  # pixels at the raw scan's 3600 dpi


def view(roll, n):
    """The frame's raw scan at screen size, kept as ansicht.npy so it is read from the full scan only once."""
    path = roll.frame_dir(n) / 'ansicht.npy'
    if not path.exists():
        save_npy(path, develop.reduce(np.load(roll.frame_dir(n) / 'rohscan.npy', mmap_mode='r'), 1600))
    return np.load(path)


def measured_base(roll, n, image=None):
    """The film base measured on frame n itself, or None; measured once and kept in the roll."""
    frame = roll.frames[n - 1]
    if 'film_base' not in frame:
        frame['film_base'] = {'measured': develop.measure_film_base(view(roll, n) if image is None else image), 'from': None}
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
    if 'levels' not in frame:
        frame['levels'] = develop.levels(view(roll, n) if image is None else image)
    return frame['levels']


def roll_balance(roll):
    """The colour negative roll's own balance over all its frames (see develop.roll_balance), else None.

    shortcut: every new frame moves the medians a little, so earlier frames' exports drift slightly until
    re-exported; freeze the balance per roll if that ever shows.
    """
    if roll.details['film_type'] != 'colour_negative' or not roll.frames:
        return None
    numbers = range(1, len(roll.frames) + 1)
    return develop.roll_balance([levels(roll, m) for m in numbers], [film_base(roll, m)[0] for m in numbers], 'colour_negative')


def params(roll, n, base, image=None):
    """The frame's auto correction, measured on its cropped screen-size scan (rotation does not matter)."""
    image = view(roll, n) if image is None else image
    cropped = develop.apply_crop(image, roll.frames[n - 1]['crop'], turn=False)
    scene = roll.frames[n - 1].get('correction', {}).get('scene', 'standard')
    return develop.analyse(cropped, roll.details['film_type'], base, roll.settings['look'], scene, roll_balance(roll))


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
