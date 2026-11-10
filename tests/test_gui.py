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
import tifffile
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from proscan import capture, develop, flat, frames, presets, scanner
from proscan import roll as rolls
from proscan.gui import i18n
from proscan.gui.rollform import RollForm
from proscan.gui.widgets import drag_crop
from proscan.gui.window import MainWindow
from tests.test_scan_core import FakeScanner, film

app = QApplication.instance() or QApplication([])


class CropDragTests(unittest.TestCase):
    START = {'x': .1, 'y': .1, 'w': .6, 'h': .6, 'free': False, 'angle': 0.}  # 3:2 on a 3:2 image is square in 0..1

    def test_move_stays_inside(self):
        self.assertEqual(drag_crop(self.START, 'move', .5, -.5, 1.5), {'x': .4, 'y': 0.})

    def test_corner_keeps_three_to_two(self):
        c = drag_crop(self.START, 'br', .2, .05, 1.5)
        self.assertAlmostEqual(c['w'] * 1.5 / c['h'], 1.5)
        self.assertEqual((c['x'], c['y']), (.1, .1))  # anchored at the opposite corner
        c = drag_crop(self.START, 'tl', -.05, -.05, 1.5)
        self.assertAlmostEqual((c['x'] + c['w'], c['y'] + c['h']), (.7, .7))

    def test_free_edge_moves_one_side(self):
        c = drag_crop({**self.START, 'free': True}, 'r', .2, .3, 1.5)
        self.assertEqual((c['x'], c['y'], c['h']), (.1, .1, .6))
        self.assertAlmostEqual(c['w'], .8)


class GuiFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Registered first, so it runs last: after close_window has let running exports finish.
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fake = FakeScanner(film(), dust=[(20, 30), (60, 90), (100, 40), (40, 130)])
        for patch in (mock.patch.object(rolls, 'ROOT', root / 'rolls'), mock.patch.object(i18n, 'SETTINGS', root / 's.json'),
                      mock.patch.object(presets, 'OWN', root / 'presets.json'), mock.patch.object(frames, 'PROFILES', root / 'filmprofile.json'),
                      mock.patch.object(flat, 'PATH', root / 'licht.npy'),
                      mock.patch.object(i18n, 'language', 'de'),
                      mock.patch.object(scanner, 'find_device', lambda: 'pieusb:test'),
                      mock.patch.object(capture, 'scan_preview', partial(capture.scan_preview, run=self.fake)),
                      mock.patch.object(capture, 'scan_raw', partial(capture.scan_raw, run=self.fake))):
            patch.start()
            self.addCleanup(patch.stop)
        self.w = MainWindow()
        self.addCleanup(self.close_window)
        self.wait(lambda: self.w.device)

    def close_window(self):
        self.w.close()  # writes pending exports and waits for them
        # Let worker threads finish before Qt objects go away, or their results arrive at deleted objects.
        for pool in (self.w.scan_pool, self.w.export_pool, self.w.probe_pool):
            pool.shutdown(wait=True)
        app.processEvents()
        # Delete the window now, while Qt is fully alive, not at interpreter exit in random order.
        self.w.probe_timer.stop()
        self.w.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

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

        steps = []
        # Connected after the window's own handler, so it reads the header once the window has updated it.
        w.bridge.progress.connect(lambda *_: steps.append(w.header.step_text.text()))
        self.scan_frame()
        self.assertIn('Vorschau … 100 %', steps)
        self.assertIn('Rohscan 1/2 … 45 %', steps)
        self.assertIn('Rohscan wird zusammengeführt … 90 %', steps)
        self.assertIsNone(w.progress)
        self.assertFalse(w.header.bar.isVisibleTo(w.header))
        self.assertEqual(len(w.roll.frames), 1)
        self.wait(lambda: w.exports.get(1, ('pending',))[0] != 'pending')
        self.assertEqual(w.exports[1][0], 'ok')
        self.assertTrue((w.roll.path / 'Export' / 'Testrolle_01.dng').exists())

        for text, key in (('+', Qt.Key.Key_Plus), ('+', Qt.Key.Key_Plus), ('7', Qt.Key.Key_7)):
            self.key(key, text)
        self.assertEqual(rolls.Roll.open(w.roll.path).frames[0]['correction'], {**develop.AUTO, 'D': 2, 'C': 1})
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2})
        for text, key in (('2', Qt.Key.Key_2), ('2', Qt.Key.Key_2), ('9', Qt.Key.Key_9)):
            self.key(key, text)  # midtones, then yellow
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2, 'Ym': 1})
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)

        # Presets: P, Down to Portrait, Enter; the keys stay. Then save as own preset and apply it later.
        # F / Shift+F and V: saturation and vibrance keys.
        self.key(Qt.Key.Key_F, 'f')
        self.key(Qt.Key.Key_F, 'f')
        self.key(Qt.Key.Key_V, 'V', Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual((w.frame(1)['correction']['F'], w.frame(1)['correction']['V']), (2, -1))
        for _ in range(3):
            self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)

        # W marks pure white and pure black and gives their share; W again turns it off.
        self.key(Qt.Key.Key_W, 'w')
        self.assertIn('Reinweiß', w.view.info[1])
        self.assertEqual(w.view.info[1], f'Reinweiß {w.clipped[0]:.1f} % · Reinschwarz {w.clipped[1]:.1f} %'.replace('.', ','))
        before = w.clipped
        for _ in range(8):
            self.key(Qt.Key.Key_Plus, '+')  # much darker: more pure black
        self.assertGreater(w.clipped[1], before[1])
        for _ in range(8):
            self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_W, 'w')
        self.assertNotIn('Reinweiß', w.view.info[1])

        # Hold Space: the plain automatic correction; let go: the frame's own again.
        mine = w.view.image
        self.key(Qt.Key.Key_Space, ' ')
        self.assertTrue(w.comparing)
        self.assertNotEqual(w.view.image, mine)
        QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, ' '))
        self.assertFalse(w.comparing)
        self.assertEqual(w.view.image, mine)

        self.key(Qt.Key.Key_P, 'p')
        items = w.preset_list()
        self.assertEqual([i[:2] for i in items[:2]], [('scene', 'standard'), ('scene', 'portrait')])
        self.assertTrue(all(not i[4].isNull() for i in items))  # every preset has its thumbnail
        self.assertEqual(w.panel.state['presets']['selected'], 0)  # the panel shows the list
        self.key(Qt.Key.Key_Down)
        self.key(Qt.Key.Key_Return)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2, 'scene': 'portrait'})
        self.key(Qt.Key.Key_H, 'h')
        with mock.patch('proscan.gui.window.QInputDialog.getText', return_value=('Mein Porträt', True)):
            self.key(Qt.Key.Key_S, 's', Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_0, '0')
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'scene': 'portrait'})  # 0 keeps the scene
        self.key(Qt.Key.Key_P, 'p')
        for _ in range(len(w.preset_list()) - 1):
            self.key(Qt.Key.Key_Down)
        self.key(Qt.Key.Key_Return)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2, 'H': 1, 'scene': 'portrait'})
        for _ in range(4):
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

        # The mouse: drag the middle of the crop to move it, Enter keeps it.
        self.key(Qt.Key.Key_A, 'a')
        w.view.grab()  # draws the hidden test window, so the view knows where the image is
        t_, c = w.view.target, w.cropping
        middle = QPointF(t_.left() + (c['x'] + c['w'] / 2) * t_.width(), t_.top() + (c['y'] + c['h'] / 2) * t_.height())
        mouse = lambda kind, pos, button: w.view.event(QMouseEvent(kind, pos, pos, button, button, Qt.KeyboardModifier.NoModifier))
        mouse(QEvent.Type.MouseButtonPress, middle, Qt.MouseButton.LeftButton)
        mouse(QEvent.Type.MouseMove, middle - QPointF(t_.width() * .02, 0), Qt.MouseButton.LeftButton)
        mouse(QEvent.Type.MouseButtonRelease, middle - QPointF(t_.width() * .02, 0), Qt.MouseButton.LeftButton)
        self.key(Qt.Key.Key_Return)
        self.assertAlmostEqual(w.frame(1)['crop']['x'], max(0, crop['x'] - .02), places=3)
        self.assertAlmostEqual(w.frame(1)['crop']['w'], crop['w'])
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)

        self.key(Qt.Key.Key_T, 't')
        self.assertEqual(w.frame(1)['crop']['turn'], 90)
        self.assertEqual(w.view.image.height() > w.view.image.width(), True)  # portrait on screen
        self.assertEqual((w.dirty, w.export_timer.isActive()), ({1}, True))  # exported 2 s after the last change
        w.flush_exports()
        self.wait(lambda: w.exports[1][0] != 'pending')
        self.assertEqual(w.exports[1][:1], ('ok',))
        for suffix in ('.tif', '.jpg', '.dng'):
            self.assertTrue((w.roll.path / 'Export' / f'Testrolle_01{suffix}').exists())
        with tifffile.TiffFile(w.roll.path / 'Export' / 'Testrolle_01.dng') as tif:
            self.assertEqual(tif.pages[0].tags[274].value, 6)
        self.key(Qt.Key.Key_T, 'T', Qt.KeyboardModifier.ShiftModifier)
        self.key(Qt.Key.Key_T, 'T', Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.frame(1)['crop']['turn'], 270)
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.frame(1)['crop']['turn'], 0)
        self.key(Qt.Key.Key_T, 't')

        self.scan_frame()
        # A new frame starts with the previous frame's crop, but upright.
        self.assertEqual(w.frame(2)['crop'], {**crop, 'turn': 0})

        w.select(1)
        self.key(Qt.Key.Key_R, 'r')
        self.assertEqual(w.step, 'rescan_load')
        self.scan_frame()
        self.assertEqual(len(w.roll.frames), 2)
        self.assertEqual(w.frame(1)['correction'], {**develop.AUTO, 'D': 2})
        self.assertEqual(len(list((w.roll.path / 'Ersetzt').iterdir())), 1)

    def test_film_stock_picked_from_the_list_sets_type_and_iso(self):
        form = RollForm('start')
        self.addCleanup(form.deleteLater)
        form.stock.setCurrentIndex(form.stock.findText('Ilford HP5 Plus 400'))
        form.stock.textActivated.emit('Ilford HP5 Plus 400')  # as a pick from the list does
        details = form.values()[0]
        self.assertEqual((details['film_stock'], details['film_type'], details['iso']), ('Ilford HP5 Plus 400', 'bw_negative', '400'))
        form.stock.setCurrentText('Agfa Vista 200')           # any other name can still be typed
        self.assertEqual(form.values()[0]['film_stock'], 'Agfa Vista 200')
        self.assertEqual(develop.film_gain('Cinestill 400D'), develop.FILM_GAINS['cinestill400d'])  # the list's names find their profile

    def test_export_folder_from_roll_settings(self):
        w = self.w
        w.create_roll({'name': 'Ordner', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        self.scan_frame()
        form = RollForm('settings', roll=w.roll)
        self.addCleanup(form.deleteLater)
        self.assertEqual(form.folder.text(), '')
        self.assertEqual(form.folder.placeholderText(), str(w.roll.path / 'Export'))
        other = Path(self.tmp.name) / 'Ausgabe'
        other.mkdir()
        with mock.patch.object(QFileDialog, 'getExistingDirectory', return_value=str(other)):
            form.choose_folder()
        w.apply_settings(*form.values())
        self.assertEqual(rolls.Roll.open(w.roll.path).settings['export']['folder'], str(other))
        self.wait(lambda: w.exports[1][0] != 'pending')
        self.assertTrue((other / 'Ordner_01.dng').exists())
        with mock.patch.object(QFileDialog, 'getExistingDirectory', return_value=str(w.roll.path / 'Export')):
            form.choose_folder()
        self.assertEqual(form.folder.text(), '')  # back to the roll's own Export/

    def test_borrowed_film_base_and_choosing_one(self):
        w = self.w
        w.create_roll({'name': 'Filmgrund', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        textured = self.fake.truth.copy()
        clear = textured.copy()
        clear[:, :6] = clear[:, -6:] = .95 * 65535  # unexposed film between frames
        for truth in (clear, textured, clear):
            self.fake.truth = truth
            self.scan_frame()
        self.assertEqual([frames.film_base(w.roll, n)[1:] for n in (1, 2, 3)], [(1, 'own'), (1, 'borrowed'), (3, 'own')])
        self.assertEqual([t['borrowed'] for t in w.strip.tiles[:3]], [False, True, False])

        w.select(2)
        self.key(Qt.Key.Key_B, 'b')
        self.assertEqual(w.choosing, 1)
        self.key(Qt.Key.Key_Right)
        self.assertEqual(w.choosing, 3)
        self.assertEqual(w.film_base(2)[1:], (3, 'chosen'))  # the screen tries the frame being chosen
        self.key(Qt.Key.Key_Return)
        self.assertIsNone(w.choosing)
        self.assertEqual(rolls.Roll.open(w.roll.path).frames[1]['film_base']['from'], 3)
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(frames.film_base(w.roll, 2)[1:], (1, 'borrowed'))
        self.key(Qt.Key.Key_B, 'b')
        self.key(Qt.Key.Key_Escape)
        self.assertEqual((w.choosing, frames.film_base(w.roll, 2)[1:]), (None, (1, 'borrowed')))

    def test_copy_and_paste_correction(self):
        w = self.w
        w.create_roll({'name': 'Kopieren', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        for _ in range(3):
            self.scan_frame()
        w.select(1)
        for text, key in (('+', Qt.Key.Key_Plus), ('9', Qt.Key.Key_9), ('*', Qt.Key.Key_Asterisk)):
            self.key(key, text)
        self.key(Qt.Key.Key_T, 't')
        self.key(Qt.Key.Key_C, 'c', Qt.KeyboardModifier.ControlModifier)
        self.assertIn('Bild 1 kopiert', w.footer.shown[1])
        wanted = {**develop.AUTO, 'D': 1, 'Y': 1, 'S': 3}

        w.select(2)
        self.key(Qt.Key.Key_V, 'v', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.frame(2)['correction'], wanted)
        self.assertEqual(w.frame(2)['crop']['turn'], 0)  # only the correction travels
        self.assertEqual(w.frame(3)['correction'], develop.AUTO)

        w.select(3)
        self.key(Qt.Key.Key_V, 'V', Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual([f['correction'] for f in rolls.Roll.open(w.roll.path).frames], [wanted] * 3)
        self.assertIn('auf 1 Bild(er)', w.footer.shown[1])  # frames 1 and 2 already had it
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.frame(3)['correction'], develop.AUTO)
        self.assertEqual(w.dirty, {3})  # exported after the usual pause; frame 2 went when frame 3 was selected

    def test_auto_lock_copied_like_a_correction(self):
        w = self.w
        w.create_roll({'name': 'Sperre', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        for _ in range(3):
            self.scan_frame()
        w.select(1)
        self.key(Qt.Key.Key_U, 'u')
        self.assertIsNone(w.frame(1).get('auto_from'))  # nothing copied yet
        w.select(2)
        self.key(Qt.Key.Key_U, 'u', Qt.KeyboardModifier.ControlModifier)
        w.select(1)
        self.key(Qt.Key.Key_U, 'u')
        self.assertEqual(w.frame(1)['auto_from'], 2)    # backwards too
        self.key(Qt.Key.Key_U, 'u', Qt.KeyboardModifier.ControlModifier)  # copies what frame 1 follows: frame 2
        w.select(3)
        self.key(Qt.Key.Key_U, 'u')
        self.assertEqual(w.frame(3)['auto_from'], 2)
        w.select(2)
        self.key(Qt.Key.Key_U, 'u')
        self.assertIsNone(w.frame(2).get('auto_from'))  # never onto itself
        w.select(1)
        self.key(Qt.Key.Key_U, 'U', Qt.KeyboardModifier.ShiftModifier)
        self.assertIsNone(w.frame(1).get('auto_from'))

    def test_neutral_spot_and_colours_from_another_frame(self):
        w = self.w
        w.create_roll({'name': 'Grau', 'film_type': 'colour_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        for _ in range(3):
            self.scan_frame()
        w.select(1)
        w.pick_neutral(.5, .5)
        self.assertIsNone(w.frame(1).get('neutral'))  # only after N
        self.key(Qt.Key.Key_N, 'n')
        self.assertEqual(w.view.mode, 'pick')
        w.view.picked.emit(.5, .5)
        self.assertEqual(len(w.frame(1)['neutral']), 2)
        self.assertFalse(w.neutral_picking)
        w.select(3)
        self.key(Qt.Key.Key_L, 'l')
        self.assertEqual(w.colour_choosing, 2)
        self.key(Qt.Key.Key_Left)
        w.select(2)                                   # no other frame while choosing
        self.assertEqual(w.sel, 3)
        self.key(Qt.Key.Key_Return)
        self.assertEqual(w.frame(3)['colour_from'], 1)
        self.assertNotEqual(w.development(3)[1], frames.params(w.roll, 3, w.development(3)[0], colour_from=3))
        w.select(1)
        self.key(Qt.Key.Key_L, 'l')
        self.key(Qt.Key.Key_Right)
        self.key(Qt.Key.Key_Right)
        self.key(Qt.Key.Key_Return)                   # frame 3 takes frame 1's: never a circle
        self.assertIsNone(w.frame(1).get('colour_from'))
        self.key(Qt.Key.Key_N, 'N', Qt.KeyboardModifier.ShiftModifier)
        self.assertIsNone(w.frame(1).get('neutral'))
        self.key(Qt.Key.Key_Z, 'z', Qt.KeyboardModifier.ControlModifier)
        self.assertIsNotNone(w.frame(1).get('neutral'))  # undo brings it back

    def test_hung_scanner_affects_only_that_frame(self):
        w = self.w
        w.create_roll({'name': 'Hängt', 'film_type': 'bw_negative'}, json.loads(json.dumps(rolls.DEFAULT_SETTINGS)))
        self.scan_frame()

        def hung(*args, **kwargs):
            raise scanner.ScannerHung('Scanner reagiert seit 360 s nicht.')
        resets = []
        with mock.patch.object(capture, 'scan_raw', hung), mock.patch.object(scanner, 'reset', resets.append):
            self.key(Qt.Key.Key_Return)
            self.wait(lambda: w.step == 'preview')
            self.key(Qt.Key.Key_Return)
            self.wait(lambda: w.step == 'fail')
            self.wait(lambda: w.reset_note)
        self.assertEqual(w.scanner_state, 'err')
        self.assertEqual(resets, ['pieusb:test'])  # reset over USB right away
        self.assertIn('zurückgesetzt', w.reset_note)
        self.key(Qt.Key.Key_7, '7')  # colour keys do nothing on black-and-white
        self.key(Qt.Key.Key_Escape)
        self.assertEqual((w.step, len(w.roll.frames)), ('load', 1))
        self.assertTrue((w.roll.frame_dir(1) / 'rohscan.npy').exists())
        self.key(Qt.Key.Key_7, '7')
        self.assertEqual(w.frame(1)['correction'], develop.AUTO)


if __name__ == '__main__':
    unittest.main()
