"""Scanning one loaded frame: the preview, then its raw scan.

A raw scan directory holds:
  rohscan.npy     float32 linear RGB in scanner counts (reference exposure)
  infrarot.npy    uint16 infrared of the reference pass (when infrared was scanned)
  staubmaske.npy  bool dust mask matching rohscan.npy (when detection succeeded)
  scan.json       settings and what happened, for later diagnosis
"""
from pathlib import Path
import shutil

import numpy as np

from . import infrared as ir
from . import multiexposure, pnm, scanner
from .files import save_json, save_npy


def scan_preview(device, path, run=scanner.run):
    """Scan the loaded frame at preview resolution; returns the image as a memmap."""
    run(scanner.preview_arguments(device, path), scanner.PREVIEW_TIMEOUT)
    return pnm.read(path)


def scan_raw(device, directory, *, infrared, multi_exposure, run=scanner.run):
    """Scan the loaded frame into the new, empty `directory`; returns the scan report.

    A frame is loaded only once, so a failed multi-exposure merge or dust
    detection falls back and is recorded instead of failing the frame.
    """
    directory = Path(directory)
    directory.mkdir(parents=True)
    passes = directory / '.durchlaeufe'
    passes.mkdir()
    report = {'dpi': scanner.RAW_DPI, 'infrared': infrared, 'multi_exposure': multi_exposure}
    try:
        reference_path = passes / '1.pnm'
        log = run(scanner.raw_arguments(device, reference_path, infrared=infrared), scanner.RAW_TIMEOUT)
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
                log = run(scanner.raw_arguments(device, longer_path, manual=longer['settings']), scanner.RAW_TIMEOUT)
                scanner.verify_settings(scanner.telemetry(log), longer['settings'])
                raw, report['merge'] = multiexposure.merge(reference, pnm.read(longer_path)[..., :3], longer['ratios'])
            except ValueError as exc:
                report['merge'] = {'status': 'skipped', 'reason': str(exc)}
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


def load_raw(directory, dust_cleaned):
    """The raw scan of a frame, dust-cleaned when asked and a dust mask exists."""
    directory = Path(directory)
    raw = np.load(directory / 'rohscan.npy', mmap_mode='r')
    mask_path = directory / 'staubmaske.npy'
    if dust_cleaned and mask_path.exists():
        return ir.repair(raw, np.load(mask_path))
    return raw
