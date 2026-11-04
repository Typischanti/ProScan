"""16-bit binary PNM files as scanimage writes them, mapped without copying.

pieusb RGBI captures carry a P6 header but four interleaved samples per pixel,
so the channel count comes from the data size, not from the magic number.
"""
import os

import numpy as np


def read(path):
    """Return a read-only (h, w, channels) big-endian uint16 memmap; channels is 1, 3 or 4."""
    with open(path, 'rb') as f:
        tokens = []
        # shortcut: header tokens are read line by line, which holds for scanimage output only
        while len(tokens) < 4:
            line = f.readline()
            if not line:
                raise ValueError('Unvollständiger PNM-Header.')
            tokens += line.split(b'#')[0].split()
        magic, w, h, maximum = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
        offset = f.tell()
        size = os.fstat(f.fileno()).st_size - offset
    if magic not in (b'P5', b'P6') or maximum != 65535 or min(w, h) < 1:
        raise ValueError('Nur 16-Bit-PNM-Scans werden unterstützt.')
    channels, rest = divmod(size, w * h * 2)
    if rest or channels not in ((1,) if magic == b'P5' else (3, 4)):
        raise ValueError('PNM-Daten unvollständig.')
    return np.memmap(path, dtype='>u2', mode='r', offset=offset, shape=(h, w, channels))


def write(path, values):
    """Write a (h, w, 3) or (h, w) uint16 array; used by tests to stand in for scanimage."""
    values = np.asarray(values)
    h, w = values.shape[:2]
    magic = 'P6' if values.ndim == 3 else 'P5'
    with open(path, 'wb') as f:
        f.write(f'{magic}\n{w} {h}\n65535\n'.encode())
        f.write(values.astype('>u2').tobytes())
