"""Scan chain checks with a stand-in for scanimage; never opens the scanner."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np
import tifffile

from proscan import capture, develop, dng, export, infrared, multiexposure, pnm, scanner
from proscan.roll import Roll

SETTINGS = {'exposure': [3000] * 4, 'gain': [19] * 4, 'offset': [0] * 4, 'light': 4, 'double': 0}
OPTIONS = 'from options --light --double-times ' + ' '.join(
    f'--exposure-time-{c} 100..10000us --gain-{c} --offset-{c}' for c in 'rgbi')
SHIFT = (1, 2)


def log(settings):
    return ('sanei_pieusb_cmd_set_gain_offset() set:\n'
            + '\n'.join(label + ' = ' + '-'.join(map(str, settings[key])) for key, label in
                        (('exposure', 'exposure times'), ('gain', 'gain'), ('offset', 'offset')))
            + f"\nlight = {settings['light']:02x}\ndouble times = {settings['double']:02x}\n")


def scene(shape=(100, 140)):
    """Linear transmission in reference counts; structure everywhere so passes align uniquely."""
    return np.random.default_rng(4).uniform(.04, .85, shape + (3,)) * 65535


def film(shape=(120, 160)):
    """Smooth like a photograph plus fine grain: dust stands out, and passes still align."""
    small = np.random.default_rng(5).uniform(.2, .6, (shape[0] // 10, shape[1] // 10, 3)).astype(np.float32)
    grain = np.random.default_rng(6).normal(0, .015, shape + (3,))
    return np.clip(cv2.resize(small, shape[::-1], interpolation=cv2.INTER_CUBIC) + grain, .04, .85) * 65535


def counts(values):
    return np.clip(np.rint(values), 0, 65535).astype(np.uint16)


class FakeScanner:
    """Writes what the CrystalScan would deliver for the given scanimage arguments."""

    def __init__(self, truth, dust=()):
        self.truth, self.dust, self.calls = truth.copy(), dust, []
        for y, x in dust:  # dust sits on the film, so it moves with it between passes
            self.truth[y:y + 2, x:x + 2] *= .5

    def __call__(self, args, timeout, progress=None):
        self.calls.append(args)
        if '--all-options' in args:
            return OPTIONS
        for value in (.25, .5, 1.) if progress else ():
            progress(value)
        output = Path(args[args.index('--output-file') + 1])
        manual = next((a for a in args if a.startswith('--exposure-time-r=')), None)
        if manual is None:
            settings, image = SETTINGS, self.truth.copy()
        else:
            exposure = [int(next(a for a in args if a.startswith(f'--exposure-time-{c}=')).split('=')[1]) for c in 'rgbi']
            settings = {**SETTINGS, 'exposure': exposure}
            ratios = np.array(exposure[:3]) / SETTINGS['exposure'][:3]
            image = np.roll(self.truth * ratios, SHIFT, (0, 1))
        if '--mode=RGBI' in args:
            ir = np.full(image.shape[:2], 40000.)
            for y, x in self.dust:
                ir[y:y + 2, x:x + 2] = 8000
            image = np.dstack([image, ir])
        pnm.write(output, counts(image))
        return log(settings)


# Option lists as scanimage --all-options prints them (abridged).
EPSON = """Options specific to device `epson2:libusb:001:004':
  Scan Mode:
    --mode Lineart|Gray|Color [Lineart]
    --depth 8|16 [8]
    --resolution 50|75|100|150|200|300|400|600|800|1200|1600|2400|3200|4800|6400dpi [50]
    --film-type Positive Film|Negative Film|Positive Slide|Negative Slide [inactive]
    --preview[=(yes|no)] [no]
  Advanced:
    --source Flatbed|Transparency Unit [Flatbed]
"""
PLUSTEK = """Options specific to device `genesys:libusb:001:005':
  Scan Mode:
    --mode Color|Gray|Lineart [Gray]
    --source Transparency Adapter|Transparency Adapter Infrared [Transparency Adapter]
    --preview[=(yes|no)] [no]
    --depth 8|16 [8]
    --resolution 900|1200|1800|3600|7200dpi [900]
"""
NIKON = """Options specific to device `coolscan3:usb:libusb:001:006':
    --preview[=(yes|no)] [no]
    --infrared[=(yes|no)] [no]
    --depth 8|16 [8]
    --resolution 4..4000dpi [4000]
    --negative[=(yes|no)] [no]
"""
CANON_LIDE = """Options specific to device `genesys:libusb:001:007':
    --mode Color|Gray|Lineart [Gray]
    --source Flatbed [Flatbed]
    --depth 8|16 [8]
    --resolution 75|150|300|600|1200dpi [75]
"""


class OtherScannerTests(unittest.TestCase):
    def test_arguments_from_the_options_the_device_lists(self):
        def args(device, text, dpi):
            return scanner.generic_arguments(device, text, 'x.pnm', dpi)[:-4]
        self.assertEqual(args('epson2:x', EPSON, 3600), ['-d', 'epson2:x', '--source=Transparency Unit', '--mode=Color',
                         '--depth=16', '--resolution=1600', '--film-type=Positive Film', '--preview=no'])
        self.assertEqual(args('genesys:x', PLUSTEK, 3600), ['-d', 'genesys:x', '--source=Transparency Adapter', '--mode=Color',
                         '--depth=16', '--resolution=3600', '--preview=no'])
        self.assertEqual(args('coolscan3:x', NIKON, 3600), ['-d', 'coolscan3:x', '--depth=16', '--resolution=3600',
                         '--negative=no', '--preview=no', '--infrared=no'])
        self.assertEqual(scanner.dpi(scanner.generic_arguments('coolscan3:x', NIKON, 'x.pnm', 600)), 600)
        with self.assertRaises(scanner.ScannerError):
            scanner.generic_arguments('genesys:y', CANON_LIDE, 'x.pnm', 3600)

    def test_finds_film_scanners_only(self):
        lists = {False: '', True: 'genesys:y\tCanon LiDE 220\nepson2:x\tEpson Perfection V600\npieusb:z\tReflecta CrystalScan 7200\n'}

        def run(args, timeout, progress=None, system=None):
            if args[0].startswith('--formatted'):
                return lists[system]
            device = args[1]
            source = next((a for a in args if a.startswith('--source=')), None)
            return {'genesys:y': CANON_LIDE, 'epson2:x': EPSON}[device] + (source or '')
        with mock.patch.object(scanner, 'run', run), mock.patch.object(scanner, '_listed', {}):
            # The system's own pieusb is not the patched driver, and the Canon flatbed has no film unit.
            self.assertEqual(scanner.find_device(), 'epson2:x')
            self.assertEqual(scanner.model('epson2:x'), 'Epson Perfection V600')
            self.assertEqual(scanner.features('epson2:x'), {'infrared': False, 'multi_exposure': False})
            self.assertEqual(scanner.dpi(scanner.raw_arguments('epson2:x', 'x.pnm')), 1600)
            with self.assertRaises(ValueError):
                scanner.raw_arguments('epson2:x', 'x.pnm', infrared=True)
            lists[False] = 'pieusb:0\tReflecta CrystalScan 7200\n'
            self.assertEqual(scanner.find_device(), 'pieusb:0')

    def test_transfer_progress_counts_fully_without_the_patched_driver(self):
        seen = []
        script = 'import sys, time\nfor p in (25, 50, 100):\n    sys.stderr.write(f"Progress: {p}.0%\\r"); sys.stderr.flush(); time.sleep(.1)\n'
        with mock.patch.object(scanner, 'SCANIMAGE', '/usr/bin/python3'):
            scanner.run(['-c', script, '-d', 'epson2:x'], 10, seen.append)
        self.assertEqual(seen, [.25, .5, 1.])


class ScannerTests(unittest.TestCase):
    def test_arguments_and_driver_log(self):
        ranges = scanner.capabilities(OPTIONS)
        longer = multiexposure.longer_pass(SETTINGS, ranges)
        self.assertEqual(longer['settings']['exposure'], [10000, 10000, 10000, 3000])
        args = scanner.raw_arguments('pieusb:0', 'x.pnm', manual=longer['settings'])
        self.assertIn('--exposure-time-r=10000', args)
        self.assertIn('--calibration=from options', args)
        self.assertIn('--resolution=3600', args)
        self.assertIn('--resolution=600', scanner.preview_arguments('pieusb:0', 'p.pnm'))
        self.assertIn('--mode=RGBI', scanner.raw_arguments('pieusb:0', 'x.pnm', infrared=True))
        with self.assertRaises(ValueError):
            scanner.raw_arguments('pieusb:0', 'x.pnm', infrared=True, manual=longer['settings'])
        self.assertEqual(scanner.telemetry(log(SETTINGS) + log(longer['settings'])), longer['settings'])
        with self.assertRaises(ValueError):
            scanner.verify_settings(longer['settings'], SETTINGS)
        with self.assertRaises(ValueError):
            scanner.telemetry('missing')
        with self.assertRaises(ValueError):
            multiexposure.longer_pass({**SETTINGS, 'exposure': [10000] * 4}, ranges)

    def test_pnm_channels(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.pnm'
            pnm.write(path, np.arange(2 * 3 * 4, dtype=np.uint16).reshape(2, 3, 4))
            data = pnm.read(path)
            self.assertEqual(data.shape, (2, 3, 4))
            self.assertEqual(int(data[1, 2, 3]), 23)
            path.write_bytes(path.read_bytes()[:-2])
            with self.assertRaises(ValueError):
                pnm.read(path)


class MultiExposureTests(unittest.TestCase):
    def test_merge_recovers_shifted_longer_pass(self):
        truth = scene()
        ratios = [3.3, 2.4, 1.8]
        merged, report = multiexposure.merge(counts(truth), counts(np.roll(truth * ratios, SHIFT, (0, 1))), ratios)
        self.assertEqual(report['shift_yx'], list(SHIFT))
        self.assertEqual(report['used_channels'], list('RGB'))
        inner = np.s_[4:-4, 4:-4]
        np.testing.assert_allclose(merged[inner], truth[inner], rtol=.002, atol=2)

    def test_dim_blue_of_an_orange_mask_is_used(self):
        # Kodak Gold 200 at the scanner's own exposure: blue stays below about 7 % of full scale.
        truth = film((400, 600)) * np.array([.5, .23, .085])
        ratios = [1.70, 2.29, 3.19]
        noise = np.random.default_rng(8)
        reference = counts(truth + noise.normal(0, 60, truth.shape))
        longer = counts(np.roll(truth * ratios, SHIFT, (0, 1)) + noise.normal(0, 60, truth.shape))
        self.assertLess(reference[..., 2].max(), .075 * 65535)
        merged, report = multiexposure.merge(reference, longer, ratios)
        self.assertEqual(report['used_channels'], list('RGB'), report['channel_reasons'])
        inner = np.s_[8:-8, 8:-8, 2]
        # The longer pass carries most of the blue, so its noise drops by about the exposure ratio.
        self.assertLess(np.std(merged[inner] - truth[inner]), np.std(reference[inner] - truth[inner]) / 2)

    def test_channel_that_ignored_the_exposure_is_not_used(self):
        truth = scene()
        actual = [3.3, 2.4, 1.0]  # blue did not get longer
        reference = counts(truth)
        merged, report = multiexposure.merge(reference, counts(np.roll(truth * actual, SHIFT, (0, 1))), [3.3, 2.4, 1.8])
        self.assertEqual(report['used_channels'], ['R', 'G'])
        np.testing.assert_allclose(merged[..., 2], reference[..., 2], rtol=1e-6)


class CropTests(unittest.TestCase):
    def test_quarter_turns_follow_the_crop(self):
        image = np.arange(4 * 6 * 3, dtype=np.float32).reshape(4, 6, 3)
        crop = {'x': 0, 'y': 0, 'w': 1, 'h': 1, 'angle': 0}
        self.assertEqual(develop.apply_crop(image, crop).shape, (4, 6, 3))
        turned = develop.apply_crop(image, {**crop, 'turn': 90})
        self.assertEqual(turned.shape, (6, 4, 3))
        np.testing.assert_array_equal(turned[0, -1], image[0, 0])  # top-left goes to top-right when turned clockwise
        np.testing.assert_array_equal(develop.apply_crop(image, {**crop, 'turn': 270})[-1, 0], image[0, 0])


class InfraredTests(unittest.TestCase):
    def test_dust_is_found_and_only_dust_repaired(self):
        rng = np.random.default_rng(1)
        image = np.full((120, 160, 3), 30000.) + rng.normal(0, 50, (120, 160, 3))
        ir = np.full((120, 160), 40000) + rng.integers(-100, 100, (120, 160))
        spots = [(20, 30), (60, 90), (100, 40), (40, 130)]
        for y, x in spots:
            image[y:y + 2, x:x + 2] = 10000
            ir[y:y + 2, x:x + 2] = 8000
        hair = np.s_[80, 60:90]  # longer than a speck: left whole, never cut into dashes
        image[hair], ir[hair] = 10000, 8000
        highlight = np.s_[10:13, 100:103]  # dense in red, infrared only slightly darker (dye crosstalk)
        image[highlight], ir[highlight] = 3000, 33000
        mask, report = infrared.dust_mask(counts(image), ir.astype(np.uint16))
        self.assertEqual(report['selected_pixels'], 4 * 16)  # each 2 x 2 speck plus one pixel all round
        for y, x in spots:
            self.assertTrue(mask[y - 1:y + 3, x - 1:x + 3].all())
        self.assertFalse(mask[78:83, 58:92].any())
        self.assertFalse(mask[8:15, 98:105].any())
        repaired = infrared.repair(image.astype(np.float32), mask)
        np.testing.assert_array_equal(repaired[~mask], image.astype(np.float32)[~mask])
        self.assertTrue(np.all(np.abs(repaired[mask] - 30000) < 500))

    def test_offset_next_to_the_best_does_not_make_it_ambiguous(self):
        # Wide specks overlap the image one pixel off too; only distant offsets decide.
        rng = np.random.default_rng(4)
        image = np.full((200, 200, 3), 30000.) + rng.normal(0, 50, (200, 200, 3))
        ir = np.full((200, 200), 40000.) + rng.normal(0, 60, (200, 200))
        for y, x in rng.integers(10, 185, (12, 2)):
            image[y:y + 4, x:x + 4] = 12000
            ir[y:y + 4, x:x + 4] = 9000
        mask, report = infrared.dust_mask(counts(image), counts(ir))
        self.assertEqual(report['shift_yx'], [0, 0])
        self.assertGreater(report['selected_pixels'], 12 * 16)

    def test_film_structure_is_rejected(self):
        ir = np.full((100, 100), 40000, np.uint16)
        ir[np.random.default_rng(2).random((100, 100)) < .05] = 8000  # far too many marks to be dust
        with self.assertRaises(infrared.InfraredRejected):
            infrared.dust_mask(counts(np.full((100, 100, 3), 30000.)), ir)


class CaptureAndRollTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self, fake, directory, **kw):
        return capture.scan_raw('pieusb:0', directory, run=fake, **{'infrared': True, 'multi_exposure': True, **kw})

    def test_raw_scan_with_infrared_and_multi_exposure(self):
        fake = FakeScanner(film(), dust=[(20, 30), (60, 90), (100, 40), (40, 130)])
        report = self.scan(fake, self.root / 'f')
        self.assertEqual(sorted(p.name for p in (self.root / 'f').iterdir()),
                         ['infrarot.npy', 'rohscan.npy', 'scan.json', 'staubmaske.npy'])
        self.assertEqual(report['merge']['used_channels'], list('RGB'))
        self.assertEqual(np.load(self.root / 'f' / 'rohscan.npy').dtype, np.float32)
        self.assertTrue(np.load(self.root / 'f' / 'staubmaske.npy')[20:22, 30:32].all())

    def test_progress_runs_through_both_passes(self):
        seen = []
        self.scan(FakeScanner(film()), self.root / 'f', progress=lambda *a: seen.append(a))
        self.assertEqual(seen[0], (.25 / 2 * .9, 1, 2))
        self.assertIn((.5 * .9, 1, 2), seen)
        self.assertEqual(seen[-1], (.9, None, 2))
        self.assertEqual([a[0] for a in seen], sorted(a[0] for a in seen))

    def test_scanimage_progress_is_parsed_while_scanning(self):
        script = self.root / 'scanimage'
        script.write_text('#!/bin/sh\nprintf "NEGATIVSTUDIO acquisition 40\\n" >&2\nsleep .2\n'
                          'printf "NEGATIVSTUDIO acquisition 100\\nProgress: 50.0%%\\r" >&2\nsleep .2\nprintf "Progress: 100.0%%\\r" >&2\n')
        script.chmod(0o755)
        seen = []
        with mock.patch.object(scanner, 'SCANIMAGE', str(script)):
            log = scanner.run([], 10, seen.append)
        self.assertEqual(seen, [.2, .75, 1.])  # only the latest value of each read counts
        self.assertIn('acquisition 40', log)
        script.write_text('#!/bin/sh\nsleep 5\n')
        with mock.patch.object(scanner, 'SCANIMAGE', str(script)), self.assertRaises(scanner.ScannerHung):
            scanner.run([], .5, seen.append)

    def test_black_and_white_single_exposure(self):
        report = self.scan(FakeScanner(scene()), self.root / 'f', infrared=False, multi_exposure=False)
        self.assertNotIn('merge', report)
        self.assertEqual(sorted(p.name for p in (self.root / 'f').iterdir()), ['rohscan.npy', 'scan.json'])

    def test_failed_merge_keeps_the_reference(self):
        flat = np.full((100, 140, 3), 20000.)  # no structure to align on
        report = self.scan(FakeScanner(flat), self.root / 'f', infrared=False)
        self.assertEqual(report['merge']['status'], 'skipped')
        self.assertTrue((self.root / 'f' / 'rohscan.npy').exists())

    def test_missing_driver_log_keeps_the_reference(self):
        fake = FakeScanner(film())
        report = self.scan(lambda args, timeout, progress=None: fake(args, timeout) and '', self.root / 'f')
        self.assertEqual(report['merge'], {'status': 'skipped', 'reason': 'Belichtungsdaten fehlen im Treiberprotokoll.'})
        self.assertTrue((self.root / 'f' / 'rohscan.npy').exists())
        self.assertEqual(scanner.environment()['SANE_DEBUG_PIEUSB'], '5')

    def test_hung_scanner_leaves_nothing_behind(self):
        def hung(args, timeout, progress=None):
            raise scanner.ScannerHung('hängt')
        with self.assertRaises(scanner.ScannerHung):
            capture.scan_raw('pieusb:0', self.root / 'f', infrared=True, multi_exposure=True, run=hung)
        self.assertFalse((self.root / 'f').exists())

    def test_roll_frames_rescan_and_dng_export(self):
        roll = Roll.create({'name': 'Hochzeit Lübeck', 'film_type': 'colour_negative', 'film_stock': 'Portra 400',
                            'notes': 'privat'}, root=self.root)
        fake = FakeScanner(film(), dust=[(20, 30), (60, 90), (100, 40), (40, 130)])
        self.assertEqual(roll.add_frame(lambda d: self.scan(fake, d)), 1)
        self.assertEqual(roll.add_frame(lambda d: self.scan(fake, d)), 2)
        self.assertEqual([f['number'] for f in Roll.open(roll.path).frames], [1, 2])

        replaced = roll.rescan_frame(2, lambda d: self.scan(fake, d))
        self.assertTrue((replaced / 'rohscan.npy').exists())
        self.assertTrue((roll.frame_dir(2) / 'rohscan.npy').exists())
        with self.assertRaises(scanner.ScannerHung):
            roll.rescan_frame(2, lambda d: (_ for _ in ()).throw(scanner.ScannerHung('x')))
        self.assertTrue((roll.frame_dir(2) / 'rohscan.npy').exists())

        paths = export.export_frame(roll, 2)
        self.assertEqual([p.name for p in paths], [f'Hochzeit Lübeck_02.{s}' for s in ('tif', 'jpg', 'dng')])
        path = paths[-1]
        with tifffile.TiffFile(paths[0]) as tif:
            self.assertEqual((tif.pages[0].dtype, tif.pages[0].shape[2]), (np.uint16, 3))
            self.assertIn('Adobe RGB'.encode('utf-16-be'), tif.pages[0].tags[34675].value)  # ICC description
        jpeg = paths[1].read_bytes()
        self.assertIn(b'ICC_PROFILE', jpeg[:2000])
        self.assertIn('Hochzeit Lübeck · Bild 2'.encode(), jpeg[:4000])
        self.assertNotIn(b'privat', jpeg)
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[0]
            self.assertEqual(page.photometric, tifffile.PHOTOMETRIC.LINEAR_RAW)
            xmp = page.tags[700].value.decode()
            data = page.asarray()
        self.assertIn('Hochzeit Lübeck · Bild 2', xmp)
        self.assertIn('Portra 400', xmp)
        self.assertNotIn(b'privat', path.read_bytes())
        raw = np.load(roll.frame_dir(2) / 'rohscan.npy')
        mask = np.load(roll.frame_dir(2) / 'staubmaske.npy')
        np.testing.assert_array_equal(data[~mask], counts(raw)[~mask])
        self.assertFalse(np.array_equal(data[mask], counts(raw)[mask]))  # dust-cleaned by default

    def test_black_and_white_roll_never_dust_cleans(self):
        roll = Roll.create({'name': 'HP5', 'film_type': 'bw_negative'}, root=self.root)
        self.assertFalse(roll.infrared)
        self.assertFalse(json.loads((roll.path / 'roll.json').read_text())['settings']['export']['dng_dust_cleaned'])
        for name in ('', '..', 'a/b'):
            with self.assertRaises(ValueError):
                Roll.create({'name': name, 'film_type': 'bw_negative'}, root=self.root)


SERIES = Path.home() / '.local/share/negativstudio/raw/series-1793531501947571534'


@unittest.skipUnless((SERIES / '03.pnm').exists(), 'recorded CrystalScan series not available')
class RecordedScanTests(unittest.TestCase):
    """A real 3600 dpi RGBI reference and +2 EV pass recorded with Negativstudio."""

    def test_real_passes_merge_on_all_channels(self):
        series = json.loads((SERIES / 'series.json').read_text())
        ratios = series['frames'][2]['ratios']
        rgbi = pnm.read(SERIES / '01.rgbi')
        merged, report = multiexposure.merge(rgbi[..., :3], pnm.read(SERIES / '03.pnm'), ratios)
        self.assertEqual(report['used_channels'], list('RGB'))
        self.assertEqual(merged.shape, (3444, 5340, 3))


if __name__ == '__main__':
    unittest.main()
