"""Presets: scenes, built-in corrections and the user's own, applied to one frame at a time.

A scene changes only the frame's scene, a correction preset replaces its key
values (the scene stays), and an own preset replaces both.
"""
from pathlib import Path
import json

from . import develop
from .files import save_json

OWN = Path.home() / '.config' / 'proscan' / 'presets.json'

CORRECTIONS = {
    'overexposed': {'D': 3},
    'underexposed': {'D': -3, 'G': -1},
    'fluorescent': {'M': 3},  # removes the green cast of fluorescent tubes
    'softer': {'G': -2},
    'harder': {'G': 2},
}
COLOUR_ONLY = {'indoor', 'fluorescent'}  # nothing to do on black-and-white film


def clean(correction):
    """Only known keys with values in range, so a hand-edited presets file cannot break a frame."""
    result = {}
    for key, value in correction.items():
        if key == 'scene' and value in develop.SCENES:
            result[key] = value
        elif key in develop.LIMITS and type(value) is int and develop.LIMITS[key][0] <= value <= develop.LIMITS[key][1]:
            result[key] = value
    return result


def own():
    """The user's own presets: [{'name', 'correction'}], shared by all rolls."""
    try:
        data = json.loads(OWN.read_text())
    except (OSError, ValueError):
        return []
    return [{'name': p['name'], 'correction': clean(p['correction'])} for p in data
            if isinstance(p, dict) and isinstance(p.get('name'), str) and isinstance(p.get('correction'), dict)]


def save_own(name, correction):
    """Save `correction` (scene and keys) as an own preset; one of the same name is replaced."""
    presets = [p for p in own() if p['name'] != name] + [{'name': name, 'correction': clean(correction)}]
    OWN.parent.mkdir(parents=True, exist_ok=True)
    save_json(OWN, presets)


def delete_own(name):
    save_json(OWN, [p for p in own() if p['name'] != name])


def available(film_type):
    """[(kind, id)] in list order: scenes, built-in corrections, own presets (id = name)."""
    bw = film_type == 'bw_negative'
    return ([('scene', s) for s in develop.SCENES if not (bw and s in COLOUR_ONLY)]
            + [('correction', c) for c in CORRECTIONS if not (bw and c in COLOUR_ONLY)]
            + [('own', p['name']) for p in own()])


def apply(kind, ident, correction):
    """The frame's correction after applying a preset to `correction`."""
    current = {**develop.AUTO, **correction}
    if kind == 'scene':
        return {**current, 'scene': ident}
    if kind == 'correction':
        return {**develop.AUTO, **CORRECTIONS[ident], 'scene': current['scene']}
    preset = next(p for p in own() if p['name'] == ident)
    return {**develop.AUTO, **preset['correction']}
