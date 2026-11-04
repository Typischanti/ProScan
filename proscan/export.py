"""Exporting a roll's frames in the formats chosen for that roll."""
import cv2
import numpy as np
import tifffile
from PySide6.QtGui import QColorSpace

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
        dng.write(written[-1], raw, roll.details, number, frame.get('crop', {}).get('turn', 0))
    return written
