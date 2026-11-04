"""The CrystalScan 7200 through scanimage and the patched pieusb driver in driver/.

The driver is loaded from this package, never from the system SANE setup, so
XSane's configuration cannot change what Pro Scan talks to.
"""
from pathlib import Path
import os
import re
import select
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SCANIMAGE = '/usr/bin/scanimage'
PREVIEW_DPI = 600
RAW_DPI = 3600
# A hung driver must not block forever; a 3600 dpi RGBI pass takes about two minutes.
PREVIEW_TIMEOUT = 120
RAW_TIMEOUT = 360


class ScannerError(Exception):
    pass


class ScannerHung(ScannerError):
    pass


def environment():
    env = os.environ.copy()
    env['SANE_CONFIG_DIR'] = str(ROOT / 'sane')
    env['LD_LIBRARY_PATH'] = str(ROOT / 'driver')
    # From level 5 on the driver logs the exposure settings it sent to the scanner (see telemetry()).
    env['SANE_DEBUG_PIEUSB'] = '5'
    env['LC_ALL'] = 'C'
    return env


# The patched driver logs how much of the image the scanner has captured; scanimage
# --progress then reports the transfer to the computer.
PROGRESS = re.compile(rb'NEGATIVSTUDIO acquisition ([0-9]+)\n|Progress:\s*([0-9]+(?:\.[0-9]+)?)%')


def _failed(log):
    lines = log.strip().splitlines()
    return ScannerError(lines[-1] if lines else 'scanimage fehlgeschlagen.')


def run(args, timeout, progress=None):
    """Run scanimage; return its stderr (driver log). `progress(fraction)` follows a scan as it runs."""
    if progress is None:
        try:
            result = subprocess.run([SCANIMAGE, *args], env=environment(), capture_output=True,
                                    text=True, errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ScannerHung(f'Scanner reagiert seit {timeout} s nicht.') from exc
        if result.returncode:
            raise _failed(result.stderr)
        return result.stderr + result.stdout
    deadline = time.monotonic() + timeout
    log = bytearray()
    last = None
    with subprocess.Popen([SCANIMAGE, *args], env=environment(), stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE) as process:
        fd = process.stderr.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise ScannerHung(f'Scanner reagiert seit {timeout} s nicht.')
            if not select.select([fd], [], [], min(remaining, 1))[0]:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            log += chunk
            # A message can be split between reads, so search the tail including the previous chunk's end.
            events = list(PROGRESS.finditer(log, max(0, len(log) - len(chunk) - 64)))
            if events:
                acquired, transferred = events[-1].groups()
                # shortcut: capture and transfer count half each; measure their real durations to weight them
                value = int(acquired) / 200 if acquired else .5 + float(transferred) / 200
                if value != last:
                    last = value
                    progress(min(1., value))
        try:
            process.wait(max(1., deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise ScannerHung(f'Scanner reagiert seit {timeout} s nicht.') from exc
    text = log.decode(errors='replace')
    if process.returncode:
        raise _failed(text)
    return text


def find_device():
    """The CrystalScan's SANE device name, or None when it is not connected."""
    text = run(['--formatted-device-list=%d%n'], 30)
    return next((line for line in text.splitlines() if line.startswith('pieusb:')), None)


def options(device, run=run):
    return run(['-d', device, '--mode=Color', '--depth=16', '--all-options', '--dont-scan'], 30)


def _arguments(device, output, dpi):
    return ['-d', device, '--mode=Color', '--depth=16', f'--resolution={dpi}',
            # The backend's own fast preview is fixed at 300 dpi; use a regular acquisition.
            '--preview=no', '--advance=no', '--clean-image=no', '--crop=None',
            '--calibration=from internal test', '--gain-adjust=* 1.0',
            '--format=pnm', '--progress', '--output-file', str(output)]


def preview_arguments(device, output):
    return _arguments(device, output, PREVIEW_DPI)


def raw_arguments(device, output, infrared=False, manual=None):
    """One pass of a raw scan: the RGBI reference pass, or a Color pass with manual exposure."""
    args = _arguments(device, output, RAW_DPI) + ['--shading-analysis=yes']
    if infrared:
        if manual is not None:
            raise ValueError('Infrarot nur im Referenzdurchlauf.')
        args[args.index('--mode=Color')] = '--mode=RGBI'
        args += ['--correct-infrared=no', '--fast-infrared=no']
    if manual is not None:
        for key, limit in (('exposure', 65535), ('gain', 63), ('offset', 255)):
            values = manual.get(key)
            if not isinstance(values, list) or len(values) != 4 or any(
                    type(v) is not int or not 0 <= v <= limit or (key == 'exposure' and not v) for v in values):
                raise ValueError('Ungültige manuelle Scannerparameter.')
        for key in ('light', 'double'):
            if type(manual.get(key)) is not int or not 0 <= manual[key] <= 255:
                raise ValueError('Ungültige Lichtparameter.')
        args[args.index('--calibration=from internal test')] = '--calibration=from options'
        for index, colour in enumerate('rgbi'):
            args += [f'--exposure-time-{colour}={manual["exposure"][index]}',
                     f'--gain-{colour}={manual["gain"][index]}', f'--offset-{colour}={manual["offset"][index]}']
        args += [f'--light={manual["light"]}', f'--double-times={manual["double"]}']
    return args


def capabilities(text):
    """Exposure limits [(low, high)] for r, g, b, i from `options()` output."""
    ranges = []
    for colour in 'rgbi':
        match = re.search(r'--exposure-time-' + colour + r'\s+(\d+)\.\.(\d+)us', text)
        if not match:
            raise ValueError('Der Scanner meldet keine manuellen Belichtungszeiten.')
        low, high = map(int, match.groups())
        if not 0 < low < high <= 65535:
            raise ValueError('Ungültiger Belichtungsbereich des Scanners.')
        ranges.append((low, high))
        for key in ('gain', 'offset'):
            if f'--{key}-{colour}' not in text:
                raise ValueError('Manuelle Verstärkung/Offset fehlen.')
    if 'from options' not in text or '--light' not in text or '--double-times' not in text:
        raise ValueError('Manuelle Kalibrierung wird nicht unterstützt.')
    return ranges


def telemetry(text):
    """The exposure settings of the last acquisition, from the driver log."""
    marker = 'sanei_pieusb_cmd_set_gain_offset() set:'
    if marker not in text:
        raise ValueError('Belichtungsdaten fehlen im Treiberprotokoll.')
    # The last SET GAIN/OFFSET record is the configuration sent for acquisition.
    block = text.rsplit(marker, 1)[1]
    result = {}
    for key, label, limit in (('exposure', 'exposure times', 65535), ('gain', 'gain', 63), ('offset', 'offset', 255)):
        match = re.search(r'\b' + label + r' = (\d+)-(\d+)-(\d+)-(\d+)', block)
        if not match:
            raise ValueError('Unvollständige Scanner-Belichtungsdaten.')
        values = list(map(int, match.groups()))
        if any(v < 0 or v > limit or (key == 'exposure' and not v) for v in values):
            raise ValueError('Ungültige Scanner-Belichtungsdaten.')
        result[key] = values
    for key, label in (('light', 'light'), ('double', 'double times')):
        match = re.search(r'\b' + label + r' = ([0-9a-fA-F]+)', block)
        if not match:
            raise ValueError('Unvollständige Scanner-Lichtparameter.')
        result[key] = int(match.group(1), 16)
    return result


def verify_settings(actual, expected):
    if any(actual[key] != expected[key] for key in ('exposure', 'gain', 'offset', 'light', 'double')):
        raise ValueError('Der Treiber hat Belichtung oder Verstärkung verändert.')
