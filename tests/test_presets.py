"""Presets: what applying each kind does, and the own presets file."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from proscan import develop, presets


class PresetTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(presets, 'OWN', Path(folder.name) / 'presets.json')
        patch.start()
        self.addCleanup(patch.stop)

    def test_apply(self):
        frame = {**develop.AUTO, 'D': 2, 'Cs': 1, 'scene': 'night'}
        self.assertEqual(presets.apply('scene', 'snow', frame), {**frame, 'scene': 'snow'})  # keys stay
        self.assertEqual(presets.apply('correction', 'overexposed', frame), {**develop.AUTO, 'D': 3, 'scene': 'night'})
        presets.save_own('Mine', {'scene': 'portrait', 'G': -1})
        self.assertEqual(presets.apply('own', 'Mine', frame), {**develop.AUTO, 'scene': 'portrait', 'G': -1})

    def test_own_presets_file(self):
        presets.save_own('A', {**develop.AUTO, 'D': 1})
        presets.save_own('A', {**develop.AUTO, 'D': 2})  # same name replaces
        presets.save_own('B', {'D': 99, 'scene': 'mars', 'X': 1, 'G': 1})  # out of range and unknown keys are dropped
        self.assertEqual([(p['name'], p['correction'].get('D'), p['correction'].get('G')) for p in presets.own()],
                         [('A', 2, 0), ('B', None, 1)])
        presets.delete_own('A')
        self.assertEqual([p['name'] for p in presets.own()], ['B'])
        presets.OWN.write_text('not json')
        self.assertEqual(presets.own(), [])

    def test_black_and_white_has_no_colour_presets(self):
        ids = [i for _, i in presets.available('bw_negative')]
        self.assertNotIn('indoor', ids)
        self.assertNotIn('fluorescent', ids)
        self.assertIn('indoor', [i for _, i in presets.available('colour_negative')])


if __name__ == '__main__':
    unittest.main()
