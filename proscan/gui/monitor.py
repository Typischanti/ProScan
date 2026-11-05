"""Showing sRGB images right on a wide-gamut monitor, with the primaries its EDID reports.

niri does no colour management, so sRGB values sent unchanged look oversaturated on a
monitor whose primaries lie beyond sRGB. The exports are never touched by this.
"""
from pathlib import Path

import numpy as np

SRGB = ((.64, .33), (.30, .60), (.15, .06), (.3127, .3290))


def primaries(edid):
    """((rx, ry), (gx, gy), (bx, by), (wx, wy)) from an EDID's chromaticity bytes 25-34."""
    lo1, lo2 = edid[25], edid[26]
    low = (lo1 >> 6, lo1 >> 4, lo1 >> 2, lo1, lo2 >> 6, lo2 >> 4, lo2 >> 2, lo2)
    v = [((edid[27 + i] << 2) | (low[i] & 3)) / 1024 for i in range(8)]
    return tuple((v[i], v[i + 1]) for i in range(0, 8, 2))


def _to_xyz(p):
    """Linear RGB -> XYZ for primaries and white point `p`."""
    xyz = np.array([[x / y, 1, (1 - x - y) / y] for x, y in p[:3]]).T
    wx, wy = p[3]
    scale = np.linalg.solve(xyz, [wx / wy, 1, (1 - wx - wy) / wy])
    return xyz * scale


def matrix(p):
    """Linear sRGB -> linear monitor RGB."""
    return np.linalg.solve(_to_xyz(p), _to_xyz(SRGB))


def connected_edid(root=Path('/sys/class/drm')):
    # shortcut: the first connected output only; with several monitors, follow the screen the window is on
    for status in sorted(root.glob('card*-*/status')):
        try:
            if status.read_text().strip() == 'connected':
                edid = (status.parent / 'edid').read_bytes()
                if len(edid) >= 128 and edid[:8] == b'\x00\xff\xff\xff\xff\xff\xff\x00':
                    return edid
        except OSError:
            continue
    return None


def _lookup():
    """(decode LUT 256, matrix, encode LUT 4096), or None when the monitor is sRGB or unknown."""
    edid = connected_edid()
    if edid is None:
        return None
    p = primaries(edid)
    if not all(0 < c < 1 for xy in p for c in xy) or np.allclose(p, SRGB, atol=.01):
        return None
    v = np.arange(256) / 255
    decode = np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4).astype(np.float32)
    v = np.arange(4096) / 4095
    encode = np.round(255 * np.where(v <= .0031308, 12.92 * v, 1.055 * v ** (1 / 2.4) - .055)).astype(np.uint8)
    return decode, matrix(p).T.astype(np.float32), encode


LOOKUP = _lookup()


def to_screen(image):
    """8-bit sRGB `image` in the monitor's own primaries (its tone curve is taken to be sRGB)."""
    if LOOKUP is None:
        return image
    decode, m, encode = LOOKUP
    linear = decode[image] @ m
    return encode[np.clip(np.rint(linear * 4095), 0, 4095).astype(np.int32)]
