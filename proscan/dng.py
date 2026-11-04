"""Raw export: a frame's raw scan as a linear DNG for developing in another program."""
from datetime import datetime
from xml.sax.saxutils import escape

import numpy as np
import tifffile

from .files import atomic

# Scanner RGB is declared as linear sRGB primaries under D65: XYZ -> camera = XYZ -> linear sRGB.
XYZ_TO_SRGB = ((3.2406, -1.5372, -0.4986), (-0.9689, 1.8758, 0.0415), (0.0557, -0.2040, 1.0570))
D65 = 21


def _srational(values, denominator=10000):
    return [v for x in values for v in (round(x * denominator), denominator)]


def xmp(details, number):
    """XMP packet with the roll details (TIFF strings are ASCII-only, roll names are not)."""
    # shortcut: details go into dc:title/dc:description only; map them to EXIF fields with the developed exports
    fields = [details.get('film_stock'), details.get('iso') and f'ISO {details["iso"]}', details.get('push_pull'),
              details.get('camera'), details.get('lens'), details.get('date'), details.get('developed_by')]
    text = ' · '.join(str(f) for f in fields if f)
    title = escape(f'{details["name"]} · Bild {number}')
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>'
            f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{escape(text)}</rdf:li></rdf:Alt></dc:description>'
            '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode()


# TIFF Orientation for a clockwise quarter turn of the image.
ORIENTATION = {0: 1, 90: 6, 180: 3, 270: 8}


def write(path, raw, details, number, turn=0):
    """Write float32 linear RGB `raw` (scanner counts) as a 16-bit LinearRaw DNG. Notes are never written.

    The pixels stay as scanned; `turn` (degrees clockwise) only sets the Orientation tag.
    """
    data = np.clip(np.rint(raw), 0, 65535).astype(np.uint16)
    tags = [
        (274, 'H', 1, ORIENTATION[turn], True),
        (271, 's', 0, 'Reflecta', True),
        (272, 's', 0, 'CrystalScan 7200', True),
        (50706, 'B', 4, (1, 4, 0, 0), True),          # DNGVersion
        (50707, 'B', 4, (1, 1, 0, 0), True),          # DNGBackwardVersion
        (50708, 's', 0, 'Reflecta CrystalScan 7200', True),
        (50717, 'I', 1, 65535, True),                 # WhiteLevel
        (50721, 10, 9, _srational(np.ravel(XYZ_TO_SRGB)), True),  # ColorMatrix1
        (50728, 5, 3, (1, 1, 1, 1, 1, 1), True),      # AsShotNeutral
        (50778, 'H', 1, D65, True),                   # CalibrationIlluminant1
    ]
    packet = xmp(details, number)
    tags.append((700, 'B', len(packet), packet, True))
    with atomic(path) as temporary:
        tifffile.imwrite(temporary, data, photometric=tifffile.PHOTOMETRIC.LINEAR_RAW, planarconfig='contig',
                         subfiletype=0, software='Pro Scan', datetime=datetime.now(), metadata=None, extratags=tags)
