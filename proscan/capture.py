"""Scanning one loaded frame: the preview, then its raw scan.

A raw scan directory holds:
  rohscan.npy     float32 linear RGB in scanner counts (reference exposure)
  infrarot.npy    uint16 infrared of the reference pass (when infrared was scanned)
  staubmaske.npy  bool dust mask matching rohscan.npy (when detection succeeded)
  scan.json       settings and what happened, for later diagnosis
"""
from pathlib import Path
import json
import shutil
import tempfile

import numpy as np

from . import infrared as ir
from . import flat, multiexposure, pnm, scanner
from .files import save_json, save_npy


def scan_preview(device, path, run=scanner.run, progress=None):
    """Scan the loaded frame at preview resolution; returns the image as a memmap.

    progress(fraction) follows the scan.
    """
    run(scanner.preview_arguments(device, path), scanner.PREVIEW_TIMEOUT, progress)
    return pnm.read(path)


def scan_raw(device, directory, *, infrared, multi_exposure, run=scanner.run, progress=None):
    """Scan the loaded frame into the new, empty `directory`; returns the scan report.

    A frame is loaded only once, so a failed multi-exposure merge or dust
    detection falls back and is recorded instead of failing the frame.
    progress(fraction, pass, passes) follows the scan; pass is None while the
    passes are merged and checked for dust.
    """
    count = 2 if multi_exposure else 1

    def stage(index):
        # The passes take the first 90 %; merging and dust detection the rest.
        return progress and (lambda f: progress((index + f) / count * .9, index + 1, count))
    directory = Path(directory)
    directory.mkdir(parents=True)
    passes = directory / '.durchlaeufe'
    passes.mkdir()
    report = {'infrared': infrared, 'multi_exposure': multi_exposure}
    try:
        reference_path = passes / '1.pnm'
        args = scanner.raw_arguments(device, reference_path, infrared=infrared)
        report['dpi'] = scanner.dpi(args)
        log = run(args, scanner.RAW_TIMEOUT, stage(0))
        data = pnm.read(reference_path)
        if data.shape[2] != (4 if infrared else 3):
            raise scanner.ScannerError('Der Scanner lieferte unerwartete Farbkanäle.')
        reference = data[..., :3]
        raw = None
        if multi_exposure:
            try:
                # Inside the fallback: without the driver log the reference pass is still a good raw scan.
                report['reference'] = scanner.telemetry(log)
                longer = multiexposure.longer_pass(report['reference'], scanner.capabilities(scanner.options(device, run)))
                longer_path = passes / '2.pnm'
                log = run(scanner.raw_arguments(device, longer_path, manual=longer['settings']), scanner.RAW_TIMEOUT, stage(1))
                scanner.verify_settings(scanner.telemetry(log), longer['settings'])
                if progress:
                    progress(.9, None, count)
                raw, report['merge'] = multiexposure.merge(reference, pnm.read(longer_path)[..., :3], longer['ratios'])
            except ValueError as exc:
                report['merge'] = {'status': 'skipped', 'reason': str(exc)}
        if progress:
            progress(.9, None, count)
        if raw is None:
            raw = np.asarray(reference, np.float32)
        save_npy(directory / 'rohscan.npy', raw)
        if infrared:
            infrared_plane = np.asarray(data[..., 3], np.uint16)
            save_npy(directory / 'infrarot.npy', infrared_plane)
            try:
                mask, report['dust'] = ir.dust_mask(reference, infrared_plane)
                save_npy(directory / 'staubmaske.npy', mask)
            except ir.InfraredRejected as exc:
                report['dust'] = {'status': 'skipped', 'reason': str(exc)}
        save_json(directory / 'scan.json', report)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    shutil.rmtree(passes)
    return report


def redetect_dust(directory):
    """Find the dust of an already scanned frame again from its saved infrared, with today's detection.

    Replaces staubmaske.npy (or removes it when nothing is found or detection refuses) and the dust
    report in scan.json; returns that report. The raw scan itself is not touched.
    """
    directory = Path(directory)
    report_path = directory / 'scan.json'
    report = json.loads(report_path.read_text())
    mask_path = directory / 'staubmaske.npy'
    try:
        mask, report['dust'] = ir.dust_mask(np.load(directory / 'rohscan.npy', mmap_mode='r'),
                                            np.load(directory / 'infrarot.npy', mmap_mode='r'))
        save_npy(mask_path, mask)
    except ir.InfraredRejected as exc:
        report['dust'] = {'status': 'skipped', 'reason': str(exc)}
        mask_path.unlink(missing_ok=True)
    report['dust'] = {k: (float(v) if isinstance(v, np.floating) else v) for k, v in report['dust'].items()}
    save_json(report_path, report)
    return report['dust']


def calibrate(device, run=scanner.run, progress=None):
    """Scan the empty film holder for the scanner's light field (see flat.py); returns the field.

    Without film far more light arrives than through any film base, so after a preview for the
    scanner's own settings the scan runs at a fraction of its exposure, shorter still while it clips.
    Only the shape of the light counts, so the exposure need not scale exactly.
    """
    with tempfile.TemporaryDirectory(prefix='proscan-licht-') as folder:
        preview = Path(folder) / 'vorschau.pnm'
        try:
            settings = scanner.telemetry(run(scanner.preview_arguments(device, preview), scanner.PREVIEW_TIMEOUT))
            ranges = scanner.capabilities(scanner.options(device, run))
        except ValueError as exc:
            raise flat.CalibrationRejected(f'Der Scanner meldet keine Belichtungswerte: {exc}') from exc
        output = Path(folder) / 'licht.pnm'
        for attempt, share in enumerate((1 / 16, 1 / 32, 1 / 64, 1 / 128)):
            if progress:
                progress((attempt + 1) / 5)
            exposure = [max(low, round(v * share)) for v, (low, _) in zip(settings['exposure'][:3], ranges)]
            manual = {**settings, 'exposure': exposure + settings['exposure'][3:]}
            run(scanner.raw_arguments(device, output, manual=manual, dpi=scanner.PREVIEW_DPI), scanner.PREVIEW_TIMEOUT)
            try:
                return flat.make(pnm.read(output)[..., :3])
            except flat.CalibrationRejected as exc:
                if 'überbelichtet' not in str(exc) or attempt == 3:
                    raise


def load_raw(directory, dust_cleaned):
    """The raw scan of a frame with the scanner's light evened out, dust-cleaned when asked and a dust mask exists."""
    directory = Path(directory)
    raw = np.load(directory / 'rohscan.npy', mmap_mode='r')
    mask_path = directory / 'staubmaske.npy'
    if dust_cleaned and mask_path.exists():
        raw = ir.repair(raw, np.load(mask_path))
    return flat.apply(raw)
