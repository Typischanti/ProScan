"""A roll: one folder holding its details, settings and the raw scans of its frames.

  roll.json        details, settings, frames
  Bilder/01/       raw scan of frame 1 (see capture.py)
  Ersetzt/         raw scans replaced by a rescan, kept until the user deletes them
  Export/          default export folder
"""
from datetime import datetime
from pathlib import Path
import json
import shutil

from .files import save_json

ROOT = Path.home() / 'Bilder' / 'Pro Scan'
FILM_TYPES = ('colour_negative', 'bw_negative', 'colour_positive')
LOOKS = ('frontier', 'faithful')
TIFF_SPACES = ('srgb', 'adobe_rgb', 'prophoto')
DETAILS = ('name', 'film_type', 'film_stock', 'iso', 'push_pull', 'camera', 'lens', 'date', 'developed_by', 'notes')

DEFAULT_SETTINGS = {
    'look': 'frontier',
    'multi_exposure': True,
    'export': {'tiff': True, 'tiff_space': 'adobe_rgb', 'jpeg': True, 'dng': True,
               'dng_dust_cleaned': True, 'folder': None},
}


def validate_name(name):
    name = name.strip()
    if not name or name in ('.', '..') or '/' in name or '\0' in name:
        raise ValueError('Ungültiger Rollenname.')
    return name


def _check(details, settings):
    if set(details) - set(DETAILS) or details.get('film_type') not in FILM_TYPES:
        raise ValueError('Ungültige Rollenangaben.')
    validate_name(details.get('name', ''))
    export = settings['export']
    if settings['look'] not in LOOKS or export['tiff_space'] not in TIFF_SPACES:
        raise ValueError('Ungültige Rolleneinstellungen.')
    # Silver in black-and-white film blocks infrared, so there is nothing to clean with.
    if details['film_type'] == 'bw_negative':
        export['dng_dust_cleaned'] = False


class Roll:
    def __init__(self, path, data):
        self.path = Path(path)
        self.details = data['details']
        self.settings = data['settings']
        self.frames = data['frames']

    @classmethod
    def create(cls, details, settings=None, root=None):
        details = {**details, 'name': validate_name(details.get('name', ''))}
        root = root or ROOT  # read at call time, so tests can redirect it
        settings = json.loads(json.dumps(settings or DEFAULT_SETTINGS))
        _check(details, settings)
        path = Path(root) / details['name']
        path.mkdir(parents=True)
        roll = cls(path, {'details': details, 'settings': settings, 'frames': []})
        roll.save()
        return roll

    @classmethod
    def open(cls, path):
        data = json.loads((Path(path) / 'roll.json').read_text())
        if data.get('version') != 1:
            raise ValueError('Unbekanntes Rollenformat.')
        return cls(path, data)

    def save(self):
        _check(self.details, self.settings)
        save_json(self.path / 'roll.json', {'version': 1, 'details': self.details,
                                           'settings': self.settings, 'frames': self.frames})

    @property
    def infrared(self):
        return self.details['film_type'] != 'bw_negative'

    @property
    def export_folder(self):
        return Path(self.settings['export']['folder'] or self.path / 'Export')

    def frame_dir(self, number):
        return self.path / 'Bilder' / f'{number:02d}'

    def add_frame(self, scan):
        """Scan the next frame with `scan(directory)`; returns its number."""
        number = len(self.frames) + 1
        scan(self.frame_dir(number))
        self.frames.append({'number': number})
        self.save()
        return number

    def rescan_frame(self, number, scan):
        """Replace a frame's raw scan; the old one moves to Ersetzt/, its correction stays."""
        current = self.frame_dir(number)
        fresh = current.with_name(current.name + '.neu')
        shutil.rmtree(fresh, ignore_errors=True)
        scan(fresh)
        replaced = self.path / 'Ersetzt' / f'Bild {number} ({datetime.now():%d.%m.%Y %H.%M.%S})'
        replaced.parent.mkdir(exist_ok=True)
        current.rename(replaced)
        fresh.rename(current)
        return replaced
