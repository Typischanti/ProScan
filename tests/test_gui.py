"""The main window's scan and correction flow, offscreen, with the stand-in scanner."""
from functools import partial
from pathlib import Path
from unittest import mock
import json
import os
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from proscan import capture, develop, scanner
from proscan import roll as rolls
from proscan.gui import i18n
from proscan.gui.window import MainWindow
from tests.test_scan_core import FakeScanner, film

app = QApplication.instance() or QApplication([])


class GuiFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fake = FakeScanner(film(), dust=[(20, 30), (60, 90), (100, 40), (40, 130)])
        for patch in (mock.patch.object(rolls, 'ROOT', root / 'rolls'), mock.patch.object(i18n, 'SETTINGS', root / 's.json'),
                      mock.patch.object(i18n, 'language', 'de'),
                      mock.patch.object(scanner, 'find_device', lambda: 'pieusb:test'),
                      mock.patch.object(capture, 'scan_preview', partial(capture.scan_preview, run=self.fake)),
                      mock.patch.object(capture, 'scan_raw', partial(capture.scan_raw, run=self.fake))):
            patch.start()
            self.addCleanup(patch.stop)
        self.w = MainWindow()
        self.addCleanup(self.w.close)
        self.wait(lambda: self.w.device)

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self, condition, timeout=30):
        end = time.time() + timeout
        while not condition():
            app.processEvents()
            if time.time() > end:
                self.fail('timed out')
            time.sleep(.01)

    def key(self, key, text='', modifiers=Qt.KeyboardModifier.NoModifier):
        self.w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))

    def scan_frame(self):
        self.key(Qt.Key.Key_Return)
        self.wait(lambda: self.w.step == 'preview')
        self.key(Qt.Key.Key_Return)
        self.wait(lambda: self.w.step == 'load')

    def test_scan_correct_crop_rescan(self):
        w = self.w
        w.create_roll({'name': 'Testrolle', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        self.assertEqual(w.step, 'load')

        self.key(Qt.Key.Key_Return)
        self.wait(lambda: w.step == 'preview')
        self.key(Qt.Key.Key_Escape)  # reload: nothing is scanned
        self.assertEqual((w.step, w.roll.frames), ('load', []))

        self.scan_frame()
        self.assertEqual(len(w.roll.frames), 1)
        self.wait(lambda: w.exports.get(1, ('pending',))[0] != 'pending')
        self.assertEqual(w.exports[1][0], 'ok')
        self.assertTrue((w.roll.path / 'Export' / 'Testrolle_01.dng').exists())

        for text, key in (('+', Qt.Key.Key_Plus), ('+', Qt.Key.Key_Plus), ('7', Qt.Key.Key_7)):
            self.key(key, text)
        self.assertEqual(rolls.Roll.open(w.roll.path).frames[0]['correction'], {**develop.AUTO, 'D': 2, 'C': 1})
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2})

        before = dict(w.frame(1)['crop'])
        self.key(Qt.Key.Key_A, 'a')
        self.key(Qt.Key.Key_Left, '', Qt.KeyboardModifier.ShiftModifier)
        self.key(Qt.Key.Key_Return)
        crop = w.frame(1)['crop']
        self.assertLess(crop['w'], before['w'])
        h, wd = np.load(w.roll.frame_dir(1) / 'rohscan.npy', mmap_mode='r').shape[:2]
        self.assertAlmostEqual(crop['w'] * wd / (crop['h'] * h), 1.5)

        self.scan_frame()
        self.assertEqual(w.frame(2)['crop'], crop)  # a new frame starts with the previous frame's crop

        w.select(1)
        self.key(Qt.Key.Key_R, 'r')
        self.assertEqual(w.step, 'rescan_load')
        self.scan_frame()
        self.assertEqual(len(w.roll.frames), 2)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2})
        self.assertEqual(len(list((w.roll.path / 'Ersetzt').iterdir())), 1)

    def test_hung_scanner_affects_only_that_frame(self):
        w = self.w
        w.create_roll({'name': 'Hängt', 'film_type': 'bw_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        self.scan_frame()

        def hung(*args, **kwargs):
            raise scanner.ScannerHung('Scanner reagiert seit 360 s nicht.')
        with mock.patch.object(capture, 'scan_raw', hung):
            self.key(Qt.Key.Key_Return)
            self.wait(lambda: w.step == 'preview')
            self.key(Qt.Key.Key_Return)
            self.wait(lambda: w.step == 'fail')
        self.assertEqual(w.scanner_state, 'err')
        self.key(Qt.Key.Key_7, '7')  # colour keys do nothing on black-and-white
        self.key(Qt.Key.Key_Escape)
        self.assertEqual((w.step, len(w.roll.frames)), ('load', 1))
        self.assertTrue((w.roll.frame_dir(1) / 'rohscan.npy').exists())
        self.key(Qt.Key.Key_7, '7')
        self.assertEqual(w.frame(1)['correction'], develop.AUTO)


if __name__ == '__main__':
    unittest.main()
