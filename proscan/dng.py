"""Raw export: a frame's raw scan as a linear DNG for developing in another program."""
from datetime import datetime
import re
from xml.sax.saxutils import escape

import numpy as np
import tifffile

from .files import atomic

# Scanner RGB is declared as linear sRGB primaries under D65: XYZ -> camera = XYZ -> linear sRGB.
XYZ_TO_SRGB = ((3.2406, -1.5372, -0.4986), (-0.9689, 1.8758, 0.0415), (0.0557, -0.2040, 1.0570))
D65 = 21


def _srational(values, denominator=10000):
    return [v for x in values for v in (round(x * denominator), denominator)]


MONTHS = {m: i + 1 for i, m in enumerate(
    'januar februar märz april mai juni juli august september oktober november dezember'.split())}
MONTHS.update({m: i + 1 for i, m in enumerate(
    'january february march april may june july august september october november december'.split())})
MONTHS.update({'jan': 1, 'feb': 2, 'mär': 3, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10,
               'oct': 10, 'nov': 11, 'dez': 12, 'dec': 12})


def xmp_date(text):
    """The roll's free-text date as an XMP date, as precise as it is given ('2025', '2025-10', '2025-10-03'), or None."""
    text = (text or '').strip().lower()
    for pattern, order in ((r'(\d{4})-(\d{1,2})-(\d{1,2})', 'ymd'), (r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})', 'dmy'),
                           (r'(\d{1,2})/(\d{4})', 'my'), (r'(\d{1,2})\.(\d{4})', 'my')):
        match = re.fullmatch(pattern, text)
        if match:
            parts = dict(zip(order, map(int, match.groups())))
            if 1 <= parts['m'] <= 12 and 1 <= parts.get('d', 1) <= 31:
                return f'{parts["y"]:04d}-{parts["m"]:02d}' + (f'-{parts["d"]:02d}' if 'd' in parts else '')
    match = re.fullmatch(r'(?:(\d{1,2})\.?\s+)?([a-zäöü]+)\.?\s+(\d{4})', text)
    if match and match.group(2) in MONTHS:
        day = f'-{int(match.group(1)):02d}' if match.group(1) else ''
        return f'{match.group(3)}-{MONTHS[match.group(2)]:02d}{day}'
    match = re.search(r'\b(\d{4})\b', text)  # at least the year, as in 'Herbst 2025'
    return match.group(1) if match else None


def xmp(details, number, camera=True):
    """XMP packet with the roll details (TIFF strings are ASCII-only, roll names are not).

    Besides title and description, the camera details go into the standard fields photo software reads:
    camera, lens, ISO, date taken, and the film stock and roll name as keywords. `camera`: False for the
    DNG, whose camera fields must stay the scanner's, as raw converters pick their colour profile by them.
    """
    fields = [details.get('film_stock'), details.get('iso') and f'ISO {details["iso"]}', details.get('push_pull'),
              details.get('camera'), details.get('lens'), details.get('date'), details.get('developed_by')]
    text = ' · '.join(str(f) for f in fields if f)
    title = escape(details['name'] if number is None else f'{details["name"]} · Bild {number}')
    props = []
    if camera and details.get('camera'):
        props.append(f'<tiff:Model>{escape(str(details["camera"]))}</tiff:Model>')
    if camera and details.get('lens'):
        props.append(f'<exifEX:LensModel>{escape(str(details["lens"]))}</exifEX:LensModel>')
    iso = str(details.get('iso') or '').strip()
    if iso.isdigit():
        props.append(f'<exif:ISOSpeedRatings><rdf:Seq><rdf:li>{iso}</rdf:li></rdf:Seq></exif:ISOSpeedRatings>')
    date = xmp_date(details.get('date'))
    if date:
        props.append(f'<exif:DateTimeOriginal>{date}</exif:DateTimeOriginal><photoshop:DateCreated>{date}</photoshop:DateCreated>')
    keywords = [str(k) for k in (details.get('film_stock'), details['name']) if k]
    props.append('<dc:subject><rdf:Bag>' + ''.join(f'<rdf:li>{escape(k)}</rdf:li>' for k in keywords) + '</rdf:Bag></dc:subject>')
    return ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:tiff="http://ns.adobe.com/tiff/1.0/" xmlns:exif="http://ns.adobe.com/exif/1.0/"'
            ' xmlns:exifEX="http://cipa.jp/exif/1.0/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">'
            f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>'
            f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{escape(text)}</rdf:li></rdf:Alt></dc:description>'
            + ''.join(props) +
            '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode()


# TIFF Orientation for a clockwise quarter turn of the image.
ORIENTATION = {0: 1, 90: 6, 180: 3, 270: 8}


def write(path, raw, details, number, turn=0, scanner='Reflecta CrystalScan 7200'):
    """Write float32 linear RGB `raw` (scanner counts) as a 16-bit LinearRaw DNG. Notes are never written.

    The pixels stay as scanned; `turn` (degrees clockwise) only sets the Orientation tag.
    """
    data = np.clip(np.rint(raw), 0, 65535).astype(np.uint16)
    make, _, model = scanner.partition(' ')
    tags = [
        (274, 'H', 1, ORIENTATION[turn], True),
        (271, 's', 0, make, True),
        (272, 's', 0, model or make, True),
        (50706, 'B', 4, (1, 4, 0, 0), True),          # DNGVersion
        (50707, 'B', 4, (1, 1, 0, 0), True),          # DNGBackwardVersion
        (50708, 's', 0, scanner, True),
        (50717, 'I', 1, 65535, True),                 # WhiteLevel
        (50721, 10, 9, _srational(np.ravel(XYZ_TO_SRGB)), True),  # ColorMatrix1
        (50728, 5, 3, (1, 1, 1, 1, 1, 1), True),      # AsShotNeutral
        (50778, 'H', 1, D65, True),                   # CalibrationIlluminant1
    ]
    packet = xmp(details, number, camera=False)
    tags.append((700, 'B', len(packet), packet, True))
    with atomic(path) as temporary:
        tifffile.imwrite(temporary, data, photometric=tifffile.PHOTOMETRIC.LINEAR_RAW, planarconfig='contig',
                         subfiletype=0, software='Pro Scan', datetime=datetime.now(), metadata=None, extratags=tags)
