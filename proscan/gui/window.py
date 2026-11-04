"""The Pro Scan main window: one roll, loaded frame by frame, corrected with keys."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import copy
import tempfile

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import capture, develop, export, scanner
from .. import roll as rolls
from ..files import save_npy
from . import i18n
from . import theme as t
from .i18n import tr
from .rollform import RollForm
from .widgets import (Card, CorrectionPanel, Footer, GridView, Header, ImageView, Legend, Strip, fmt, label,
                      qimage, scoped, wrapped)

# Number pad (and main-row) keys -> correction key and step; see docs/design legend.
PAD = {'+': ('D', 1), '-': ('D', -1), '7': ('C', 1), '4': ('C', -1), '8': ('M', 1), '5': ('M', -1),
       '9': ('Y', 1), '6': ('Y', -1), '3': ('G', 1), '1': ('G', -1), '*': ('S', 1), '/': ('S', -1)}
BUSY = ('preview_run', 'raw')


class Bridge(QObject):
    """Delivers worker-thread results to the GUI thread."""
    done = Signal(object, object, object)


def number(value, unit=''):
    text = f'{value:+.1f}'.replace('-', '−').replace('+', '+' if value else '±')
    return (text.replace('.', ',') if i18n.language == 'de' else text) + unit


def recent_rolls(limit=6):
    paths = [p for p in rolls.ROOT.glob('*/roll.json')] if rolls.ROOT.exists() else []
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in paths[:limit]:
        try:
            roll = rolls.Roll.open(path.parent)
        except (OSError, ValueError, KeyError):
            continue
        result.append((roll, f'{len(roll.frames)} {tr("frames")} · {tr(roll.details["film_type"])}'))
    return result


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Pro Scan')
        self.resize(1600, 1000)
        self.bridge = Bridge()
        self.bridge.done.connect(lambda callback, result, error: callback(result, error))
        self.scan_pool, self.export_pool, self.probe_pool = (ThreadPoolExecutor(1) for _ in range(3))
        self.work = tempfile.TemporaryDirectory(prefix='proscan-')
        self.roll = None
        self.device = None
        self.scanner_state = 'off'
        self.probing = False
        self.step = 'none'
        self.target = None
        self.sel = None
        self.grid = False
        self.cropping = None
        self.preview = None
        self.failure = ''
        self.rescanning = False
        self.form = None
        self.raw_cache = {}
        self.images = {}
        self.thumbs = {}
        self.undo, self.redo = {}, {}
        self.exports = {}

        central = QWidget()
        central.setObjectName('page')
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = Header()
        self.header.grid_clicked.connect(self.toggle_grid)
        self.header.settings_clicked.connect(self.open_settings)
        self.header.language_clicked.connect(self.toggle_language)
        layout.addWidget(self.header)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.stack = QStackedWidget()
        self.view = ImageView()
        self.gridview = GridView()
        self.gridview.frame_clicked.connect(self.select)
        self.card = Card()
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.gridview)
        self.stack.addWidget(self.card)
        body.addWidget(self.stack, 1)
        self.panel = CorrectionPanel()
        self.panel.reset_clicked.connect(self.reset_frame)
        body.addWidget(self.panel)
        layout.addLayout(body, 1)
        self.strip = Strip()
        self.strip.frame_clicked.connect(self.select)
        layout.addWidget(self.strip)
        self.footer = Footer()
        layout.addWidget(self.footer)
        for widget in central.findChildren(QWidget):
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.probe_timer = QTimer(self)
        self.probe_timer.timeout.connect(self.probe)
        self.probe_timer.start(5000)
        self.probe()
        self.refresh()

    # --- workers -----------------------------------------------------------------------------

    def run(self, pool, function, callback):
        future = pool.submit(function)
        future.add_done_callback(lambda f: self.bridge.done.emit(
            callback, None if f.exception() else f.result(), f.exception()))

    def probe(self):
        if self.probing or self.step in BUSY:
            return
        self.probing = True
        self.run(self.probe_pool, scanner.find_device, self.probed)

    def probed(self, device, error):
        self.probing = False
        self.device = None if error else device
        if self.scanner_state != 'err' or self.device:
            self.scanner_state = 'ok' if self.device else 'off'
        self.refresh()

    # --- rolls ---------------------------------------------------------------------------------

    def new_roll(self):
        recent = recent_rolls()
        defaults = (recent[0][0].details['name'], recent[0][0].settings) if recent else None
        self.show_form(RollForm('start', recent=[(r.path, meta) for r, meta in recent], defaults=defaults))

    def show_form(self, form):
        self.close_form()
        self.form = form
        form.accepted.connect(self.create_roll)
        form.cancelled.connect(lambda: (self.close_form(), self.refresh()))
        form.open_requested.connect(self.open_roll)
        self.stack.addWidget(form)
        self.stack.setCurrentWidget(form)
        self.panel.hide()
        self.strip.hide()
        self.footer.hide()
        self.header.update_state(tr('new_roll'), '', '', '', t.GREEN, *self.scanner_text(), False, False, i18n.language)
        form.name.setFocus()

    def close_form(self):
        if self.form:
            self.stack.removeWidget(self.form)
            self.form.deleteLater()
            self.form = None
            self.setFocus()

    def create_roll(self, details, settings):
        try:
            roll = rolls.Roll.create(details, settings)
        except (OSError, ValueError) as exc:
            self.form.error.setText(str(exc) if not isinstance(exc, FileExistsError) else f'„{details["name"]}“ existiert bereits.')
            return
        self.close_form()
        self.set_roll(roll)

    def open_roll(self, path=None):
        if path is None:
            path = QFileDialog.getExistingDirectory(self, tr('open_roll'), str(rolls.ROOT))
            if not path:
                return
        try:
            roll = rolls.Roll.open(path)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, tr('error'), str(exc))
            return
        self.close_form()
        self.set_roll(roll)

    def set_roll(self, roll):
        self.roll = roll
        self.raw_cache.clear()
        self.images.clear()
        self.thumbs.clear()
        self.undo.clear()
        self.redo.clear()
        self.exports.clear()
        for frame in roll.frames:
            # Frames scanned from the command line carry no correction or crop yet.
            frame.setdefault('correction', dict(develop.AUTO))
            if 'crop' not in frame:
                frame['crop'] = develop.default_crop(np.load(roll.frame_dir(frame['number']) / 'rohscan.npy', mmap_mode='r').shape)
            if (roll.export_folder / (export.file_stem(roll, frame['number']) + '.dng')).exists():
                self.exports[frame['number']] = ('ok', '', 'DNG')
        self.sel = roll.frames[-1]['number'] if roll.frames else None
        self.step = 'load'
        self.grid = False
        self.cropping = None
        self.refresh()

    def open_settings(self):
        if not self.roll:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('roll_settings'))
        dialog.resize(1180, 800)
        form = RollForm('settings', roll=self.roll)
        form.cancelled.connect(dialog.accept)
        QVBoxLayout(dialog).addWidget(form)
        dialog.layout().setContentsMargins(0, 0, 0, 0)
        dialog.exec()
        details, settings = form.values()
        details['name'] = self.roll.details['name']
        if details['film_type'] != self.roll.details['film_type'] and self.roll.frames:
            answer = QMessageBox.question(self, tr('cf_title'), f'{tr(self.roll.details["film_type"])} → {tr(details["film_type"])}\n\n'
                                          f'{len(self.roll.frames)} {tr("cf_count")}. {tr("cf_keep")}')
            if answer != QMessageBox.StandardButton.Yes:
                details['film_type'] = self.roll.details['film_type']
        export_changed = settings['export'] != self.roll.settings['export'] or details['film_type'] != self.roll.details['film_type']
        self.roll.details, self.roll.settings = details, settings
        self.roll.save()
        self.images.clear()
        if export_changed:
            for frame in self.roll.frames:
                self.export(frame['number'])
        self.refresh()

    # --- scanning ------------------------------------------------------------------------------

    def start_preview(self):
        if not self.roll or self.step not in ('load', 'rescan_load'):
            return
        if not self.device:
            self.probe()
            return
        rescan = self.step == 'rescan_load'
        self.target = self.target if rescan else len(self.roll.frames) + 1
        self.step = 'preview_run'
        self.rescanning = rescan
        path = Path(self.work.name) / 'vorschau.pnm'
        self.run(self.scan_pool, lambda: capture.scan_preview(self.device, path), self.preview_done)
        self.refresh()

    def preview_done(self, preview, error):
        if error:
            return self.scan_failed(error)
        image = (np.clip(np.asarray(preview[..., :3], np.float32) / 65535, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
        self.preview = qimage(image)
        self.step = 'preview'
        self.refresh()

    def confirm_preview(self):
        self.step = 'raw'
        self.scanner_state = 'busy'
        roll, n, device = self.roll, self.target, self.device

        def scan(directory):
            return capture.scan_raw(device, directory, infrared=roll.infrared, multi_exposure=roll.settings['multi_exposure'])

        if self.rescanning:
            self.run(self.scan_pool, lambda: roll.rescan_frame(n, scan), self.raw_done)
        else:
            self.run(self.scan_pool, lambda: scan(roll.frame_dir(n)), self.raw_done)
        self.refresh()

    def raw_done(self, result, error):
        if error:
            return self.scan_failed(error)
        self.scanner_state = 'ok'
        n = self.target
        if not self.rescanning:
            shape = np.load(self.roll.frame_dir(n) / 'rohscan.npy', mmap_mode='r').shape
            previous = self.roll.frames[-1].get('crop') if self.roll.frames else None
            self.roll.frames.append({'number': n, 'correction': dict(develop.AUTO),
                                     'crop': dict(previous) if previous else develop.default_crop(shape)})
            self.roll.save()
        self.raw_cache.pop(n, None)
        self.images.pop(n, None)
        self.thumbs.pop(n, None)
        self.sel = n
        self.step = 'load'
        self.rescanning = False
        self.export(n)
        self.refresh()

    def scan_failed(self, error):
        self.failure = str(error)
        self.scanner_state = 'err' if isinstance(error, scanner.ScannerHung) else ('ok' if self.device else 'off')
        self.step = 'fail'
        self.refresh()

    def retry_scan(self):
        # The frame is still loaded and its preview was confirmed: find the scanner again and scan.
        self.device = None
        self.step = 'raw'
        self.scanner_state = 'busy'

        def found(device, error):
            if error or not device:
                return self.scan_failed(error or scanner.ScannerError(tr('scanner_off')))
            self.device = device
            self.confirm_preview()
        self.run(self.probe_pool, scanner.find_device, found)
        self.refresh()

    def skip(self):
        self.step = 'load'
        self.rescanning = False
        self.preview = None
        self.refresh()

    def rescan(self):
        if self.roll and self.sel and self.step == 'load':
            self.target = self.sel
            self.step = 'rescan_load'
            self.refresh()

    # --- exports -------------------------------------------------------------------------------

    def export(self, n):
        # shortcut: only the DNG exists, and it does not depend on corrections; re-export on correction once TIFF/JPEG exist
        if not self.roll.settings['export']['dng']:
            self.exports.pop(n, None)
            return
        self.exports[n] = ('pending',)
        roll = self.roll

        def done(_, error):
            if roll is self.roll:
                self.exports[n] = ('fail', str(error)) if error else ('ok', datetime.now().strftime('%H:%M'), 'DNG')
                self.refresh()
        self.run(self.export_pool, lambda: export.export_frame(roll, n), done)

    # --- frames and corrections ----------------------------------------------------------------

    def frame(self, n):
        return self.roll.frames[n - 1]

    def raw(self, n):
        """The frame's raw scan at screen size; kept as ansicht.npy so opening a roll never reads full scans twice."""
        if n not in self.raw_cache:
            if len(self.raw_cache) > 8:
                self.raw_cache.pop(next(iter(self.raw_cache)))
            path = self.roll.frame_dir(n) / 'ansicht.npy'
            if not path.exists():
                save_npy(path, develop.reduce(np.load(self.roll.frame_dir(n) / 'rohscan.npy', mmap_mode='r'), 1600))
            self.raw_cache[n] = np.load(path)
        return self.raw_cache[n]

    def _developed(self, cache, n, raw):
        frame = self.frame(n)
        key = (repr(frame['correction']), repr(frame['crop']), self.roll.details['film_type'])
        if cache.get(n, (None,))[0] != key:
            image = develop.develop(develop.apply_crop(raw, frame['crop']), self.roll.details['film_type'], frame['correction'])
            cache[n] = (key, qimage(image))
        return cache[n][1]

    def image(self, n):
        """Developed, cropped view of frame n, cached per correction and crop."""
        return self._developed(self.images, n, self.raw(n))

    def thumb(self, n):
        if n not in self.raw_cache and not (self.roll.frame_dir(n) / 'ansicht.npy').exists():
            self.raw(n)
        small = np.load(self.roll.frame_dir(n) / 'ansicht.npy', mmap_mode='r')[::6, ::6]
        return self._developed(self.thumbs, n, np.asarray(small, np.float32))

    def select(self, n):
        if self.roll and 1 <= n <= len(self.roll.frames) and not self.cropping:
            self.sel = n
            self.refresh()

    def change(self, n, correction=None, crop=None):
        frame = self.frame(n)
        self.undo.setdefault(n, []).append((dict(frame['correction']), dict(frame['crop'])))
        self.redo[n] = []
        if correction is not None:
            frame['correction'] = correction
        if crop is not None:
            frame['crop'] = crop
        self.roll.save()
        self.refresh()

    def key_step(self, key, delta):
        if not self.can_correct() or (key in 'CMY' and self.roll.details['film_type'] == 'bw_negative'):
            return
        correction = dict(self.frame(self.sel)['correction'])
        low, high = develop.LIMITS[key]
        value = max(low, min(high, correction[key] + delta))
        if value != correction[key]:
            correction[key] = value
            self.change(self.sel, correction=correction)

    def reset_frame(self):
        if self.can_correct() and self.frame(self.sel)['correction'] != develop.AUTO:
            self.change(self.sel, correction=dict(develop.AUTO))

    def history(self, back):
        if not self.can_correct():
            return
        source, target = (self.undo, self.redo) if back else (self.redo, self.undo)
        if source.get(self.sel):
            frame = self.frame(self.sel)
            target.setdefault(self.sel, []).append((dict(frame['correction']), dict(frame['crop'])))
            frame['correction'], frame['crop'] = source[self.sel].pop()
            self.roll.save()
            self.refresh()

    def can_correct(self):
        return bool(self.roll and self.sel and self.step not in ('preview', 'preview_run', 'fail') and not self.cropping)

    # --- crop mode -----------------------------------------------------------------------------

    def start_crop(self):
        if self.can_correct():
            self.grid = False
            self.cropping = dict(self.frame(self.sel)['crop'])
            self.refresh()

    def crop_key(self, event):
        c = self.cropping
        key, shift = event.key(), event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        raw = self.raw(self.sel)
        aspect = raw.shape[1] / raw.shape[0]
        step = .005
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cropping = None
            self.change(self.sel, crop=c)
            return
        if key == Qt.Key.Key_Escape:
            self.cropping = None
        elif key == Qt.Key.Key_Delete:
            self.cropping = develop.default_crop(raw.shape)
        elif event.text().lower() == 'f':
            c['free'] = not c['free']
        elif event.text() in ('[', ']'):
            c['angle'] = round(max(-5, min(5, c['angle'] + (.1 if event.text() == '[' else -.1))), 1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(key, 0)
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(key, 0) * aspect
            if shift:
                cx, cy = c['x'] + c['w'] / 2, c['y'] + c['h'] / 2
                grow = 2 * (dx or (step if key == Qt.Key.Key_Down else -step) if not c['free'] else dx)
                if c['free']:
                    w, h = c['w'] + grow, c['h'] + 2 * dy
                else:
                    # Keep 3:2 (or 2:3) in scan pixels: h = w * aspect / ratio.
                    ratio = 1.5 if c['w'] * aspect >= c['h'] else 1 / 1.5
                    w = min(c['w'] + grow, ratio / aspect)
                    h = w * aspect / ratio
                w, h = max(.1, min(1, w)), max(.1, min(1, h))
                c.update(w=w, h=h, x=cx - w / 2, y=cy - h / 2)
            else:
                c['x'] += dx
                c['y'] += dy
            c['x'] = max(0, min(1 - c['w'], c['x']))
            c['y'] = max(0, min(1 - c['h'], c['y']))
        self.refresh()

    # --- keyboard ------------------------------------------------------------------------------

    def keyPressEvent(self, event):
        if self.form:
            return super().keyPressEvent(event)
        key, mods, text = event.key(), event.modifiers(), event.text()
        ctrl = mods & Qt.KeyboardModifier.ControlModifier
        enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if key == Qt.Key.Key_F1:
            Legend(self).exec()
        elif ctrl and key == Qt.Key.Key_N:
            self.new_roll()
        elif ctrl and key == Qt.Key.Key_O:
            self.open_roll()
        elif not self.roll:
            return super().keyPressEvent(event)
        elif ctrl and key == Qt.Key.Key_Z:
            self.history(back=not mods & Qt.KeyboardModifier.ShiftModifier)
        elif ctrl and key == Qt.Key.Key_Y:
            self.history(back=False)
        elif ctrl and key == Qt.Key.Key_E:
            if self.sel:
                self.export(self.sel)
                self.refresh()
        elif ctrl and key == Qt.Key.Key_Comma:
            self.open_settings()
        elif self.cropping:
            self.crop_key(event)
        elif enter and self.grid:
            self.toggle_grid()
        elif enter:
            {'load': self.start_preview, 'rescan_load': self.start_preview, 'preview': self.confirm_preview,
             'fail': self.retry_scan}.get(self.step, lambda: None)()
        elif key == Qt.Key.Key_Escape:
            if self.grid:
                self.toggle_grid()
            elif self.step in ('preview', 'fail', 'rescan_load'):
                self.skip()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.sel:
            self.select(self.sel + (1 if key == Qt.Key.Key_Right else -1))
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.grid and self.sel:
            self.select(self.sel + (4 if key == Qt.Key.Key_Down else -4))
        elif text.lower() == 'g' or text == ',':
            self.toggle_grid()
        elif text.lower() == 'a':
            self.start_crop()
        elif text.lower() == 'r':
            self.rescan()
        elif text == '0':
            self.reset_frame()
        elif text in PAD:
            self.key_step(*PAD[text])
        else:
            super().keyPressEvent(event)

    def toggle_grid(self):
        if self.roll and self.roll.frames and not self.cropping:
            self.grid = not self.grid
            self.refresh()

    def toggle_language(self):
        i18n.set_language('en' if i18n.language == 'de' else 'de')
        if self.form and self.form.mode == 'start':
            self.new_roll()
        self.refresh()

    # --- rendering -----------------------------------------------------------------------------

    def scanner_text(self):
        return tr('scanner_' + self.scanner_state), {'ok': t.GREEN, 'busy': t.BLUE, 'err': t.RED, 'off': t.RED}[self.scanner_state]

    def export_status(self, n):
        state = self.exports.get(n)
        if not state:
            return '–', '#6e6e6e', tr('no_export')
        if state[0] == 'pending':
            return '…', '#9a9a9a', tr('export_pending', formats='DNG')
        if state[0] == 'fail':
            return '!', t.RED, tr('export_failed')
        return '✓', t.GREEN, tr('exported', time=state[1], formats=state[2]).replace('  ', ' ')

    def refresh(self):
        if self.form:
            return
        roll = self.roll
        has = roll is not None
        self.panel.setVisible(has and not self.cropping)
        self.strip.setVisible(has)
        self.footer.setVisible(True)
        steps = {'none': tr('step_none'), 'load': tr('step_load'), 'preview_run': tr('step_preview_run'),
                 'preview': tr('step_preview'), 'raw': tr('step_raw'), 'fail': tr('step_fail'),
                 'rescan_load': tr('step_rescan', n=self.target or 0), 'preview_rescan': tr('step_rescan_preview')}
        step = 'preview_rescan' if self.step == 'preview' and self.rescanning else self.step
        accent = {'load': t.TEXT, 'rescan_load': t.AMBER, 'preview_run': t.AMBER, 'preview': t.AMBER, 'raw': t.BLUE,
                  'fail': t.RED}.get(self.step, t.GREEN if self.device else t.RED)
        n_step = self.target if self.step != 'load' else (len(roll.frames) + 1 if has else None)
        meta = ''
        if has:
            d = roll.details
            meta = ' · '.join(x for x in (d.get('film_stock'), tr(d['film_type']), tr(roll.settings['look'])) if x)
        self.header.update_state(roll.details['name'] if has else '—', meta,
                                 f'{tr("frame")} {n_step}' if has and n_step else '', steps[step] if has else tr('step_none'),
                                 accent, *self.scanner_text(), has, self.grid, i18n.language)
        self.footer.update_state(tr('foot') if has else tr('foot')[-1:], tr('autosave') if has else '')
        if not has:
            return self.render_empty()
        if self.step == 'fail':
            self.render_failure()
        elif self.step == 'preview' and self.preview:
            n = self.target
            title = f'{tr("frame")} {n}' + (' · ' + tr('rescan') if self.rescanning else '')
            self.view.show(self.preview, 'preview', info=(tr('preview_lowres'), tr('preview_not_saved')),
                           preview=(title, tr('rescan') if self.rescanning else tr('scan'),
                                    tr('cancel_rescan') if self.rescanning else tr('reload')))
            self.stack.setCurrentWidget(self.view)
        elif self.cropping:
            frame = self.frame(self.sel)
            raw = develop.rotate(self.raw(self.sel), self.cropping['angle'])
            image = qimage(develop.develop(raw, roll.details['film_type'], frame['correction']))
            self.view.show(image, 'crop', crop=self.cropping, info=(tr('crop_mode'), '  ·  '.join(
                f'{key} {text}' for text, key in tr('crop_keys')) + '  ·  Enter / Esc'))
            self.stack.setCurrentWidget(self.view)
        elif self.grid:
            page = (self.sel - 1) // 12 * 12
            tiles = []
            for frame in roll.frames[page:page + 12]:
                n, c = frame['number'], frame['correction']
                glyph, color, _ = self.export_status(n)
                tiles.append({'n': n, 'image': self.image(n), 'selected': n == self.sel, 'corrected': c != develop.AUTO,
                              'values': f'D{fmt(c["D"]):>3}  C{fmt(c["C"]):>3}  M{fmt(c["M"]):>3}  Y{fmt(c["Y"]):>3}  S {c["S"]}',
                              'export': glyph, 'export_color': color})
            self.gridview.update_state(tr('grid_title', a=page + 1, b=page + len(tiles)), tiles)
            self.stack.setCurrentWidget(self.gridview)
        else:
            if self.sel:
                frame = self.frame(self.sel)
                raw = self.raw(self.sel)
                full_w = np.load(roll.frame_dir(self.sel) / 'rohscan.npy', mmap_mode='r').shape
                px = f'{round(frame["crop"]["w"] * full_w[1])} × {round(frame["crop"]["h"] * full_w[0])} px'
                self.view.show(self.image(self.sel), info=(f'{tr("frame")} {self.sel} · {scanner.RAW_DPI} dpi · {px}',
                                                           self.crop_text(frame['crop'])))
            else:
                self.view.show(None)
            self.stack.setCurrentWidget(self.view)
        self.render_panel()
        self.render_strip()

    def crop_text(self, crop):
        return f'{tr("free") if crop["free"] else tr("locked")} · {number(crop["angle"], "°")}'

    def render_panel(self):
        locked = not self.can_correct()
        if not self.sel or locked:
            values, corrected, crop = dict(develop.AUTO), False, '—'
        else:
            frame = self.frame(self.sel)
            values, corrected, crop = frame['correction'], frame['correction'] != develop.AUTO, self.crop_text(frame['crop'])
        frame_label = f'{tr("frame")} {self.target if locked and self.step in ("preview", "fail") else self.sel or ""}'
        self.panel.update_state({'frame': frame_label, 'status': '' if locked else '· ' + tr('corrected' if corrected else 'auto'),
                                 'corrected': corrected and not locked, 'values': values, 'locked': locked,
                                 'bw': self.roll.details['film_type'] == 'bw_negative', 'crop': '—' if locked else crop,
                                 'export': self.export_status(self.sel) if self.sel and not locked else ('–', '#6e6e6e', tr('no_export'))})

    def render_strip(self):
        tiles = []
        for frame in self.roll.frames:
            n = frame['number']
            glyph, color, _ = self.export_status(n)
            state = 'done'
            if self.rescanning and n == self.target and self.step in ('preview', 'raw', 'fail'):
                state = {'preview': 'preview', 'raw': 'scanning', 'fail': 'failed'}[self.step]
            tiles.append({'n': n, 'image': self.thumb(n), 'state': state, 'selected': n == self.sel and not self.grid,
                          'corrected': frame['correction'] != develop.AUTO, 'export': glyph, 'export_color': color})
        if not self.rescanning:
            state = {'preview_run': 'preview', 'preview': 'preview', 'raw': 'scanning', 'fail': 'failed'}.get(self.step, 'empty')
            tiles.append({'n': len(self.roll.frames) + 1, 'image': None, 'state': state,
                          'selected': self.step in ('preview', 'fail') or not self.sel, 'corrected': False})
        self.strip.update_state(tiles)

    def render_failure(self):
        n = self.target
        self.card.clear()
        scoped(self.card.box, 'card', f'background: #1f1f1f; border: 1px solid #3a3a3a; border-top: 3px solid {t.RED}; border-radius: 4px;')
        c = self.card.content
        c.setContentsMargins(30, 28, 30, 28)
        c.addWidget(label(tr('fail_title'), 22))
        c.addWidget(wrapped(tr('fail_body', n=n, reason=self.failure), 14, '#a3a3a3'))
        c.addWidget(wrapped(tr('fail_safe1', n=n) + '\n' + tr('fail_safe2'), 14, '#d0d0d0'))
        for text, primary in ((tr('fail_action', n=n) + '      Enter', True), (tr('fail_skip', n=n) + '      Esc', False)):
            button = QPushButton(text)
            button.setProperty('primary', primary)
            button.clicked.connect(self.retry_scan if primary else self.skip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            c.addWidget(button)
        self.stack.setCurrentWidget(self.card)

    def render_empty(self):
        self.panel.hide()
        self.card.clear()
        self.card.box.setFixedWidth(640)
        scoped(self.card.box, 'card', 'background: transparent;')
        c = self.card.content
        c.setContentsMargins(0, 0, 0, 0)
        c.addWidget(label(tr('no_roll'), 28))
        c.addWidget(wrapped(tr('empty_ok') if self.device else tr('empty_off'), 15, '#a3a3a3'))
        if not self.device:
            notice = wrapped(f'<span style="color:{t.RED}">●</span>&nbsp; {tr("off_title")}<br>'
                             f'<span style="color:#a3a3a3;font-size:13px">{tr("off_body")}</span>', 15)
            notice.setStyleSheet('background: #1f1f1f; border: 1px solid #3a3a3a; border-radius: 3px; padding: 14px 16px;')
            c.addWidget(notice)
        buttons = QHBoxLayout()
        for text, action, primary in ((tr('new_roll') + '    Ctrl+N', self.new_roll, True),
                                      (tr('open_roll') + '    Ctrl+O', lambda: self.open_roll(), False)):
            button = QPushButton(text)
            button.setProperty('primary', primary)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(action)
            buttons.addWidget(button)
        buttons.addStretch()
        c.addLayout(buttons)
        recent = recent_rolls(3)
        if recent:
            c.addWidget(label(tr('recent').upper(), 12, t.DIM))
            for roll, meta in recent:
                button = QPushButton(f'{roll.details["name"]}      {meta}')
                button.setStyleSheet('text-align: left; border: none; border-bottom: 1px solid #2a2a2a; padding: 10px 12px;')
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda _=False, p=roll.path: self.open_roll(str(p)))
                c.addWidget(button)
        self.stack.setCurrentWidget(self.card)

    def closeEvent(self, event):
        for pool in (self.scan_pool, self.export_pool, self.probe_pool):
            pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
