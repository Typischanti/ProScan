"""Film scanners through scanimage.

Reflecta/PIE scanners (CrystalScan, ProScan, DigitDia) use the patched pieusb
driver in driver/, loaded from this package, never from the system SANE setup,
so XSane's configuration cannot change what Pro Scan talks to. Only these give
infrared and multi-exposure. Nikon Coolscan, Plustek OpticFilm and Epson
Perfection scanners use the system's SANE backends with the options each
device lists itself (see generic_arguments).
"""
from pathlib import Path
import os
import re
import select
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SCANIMAGE = shutil.which('scanimage') or '/usr/bin/scanimage'  # Homebrew puts it elsewhere on macOS
PREVIEW_DPI = 600
RAW_DPI = 3600
# A hung driver must not block forever; a 3600 dpi RGBI pass takes about two minutes.
PREVIEW_TIMEOUT = 120
RAW_TIMEOUT = 360


class ScannerError(Exception):
    pass


class ScannerHung(ScannerError):
    pass


# Backends besides pieusb, and what they scan film with. Flatbeds scan their whole film area.
BACKENDS = {'coolscan3': 'film', 'genesys': 'transparency', 'epson2': 'flatbed', 'epsonds': 'flatbed'}
# shortcut: flatbeds scan the whole film holder, so their raw scan is kept at 1600 dpi; scan one frame's area once the preview can mark it
FLATBED_DPI = 1600
models = {}  # device -> 'Vendor Model', filled by find_device


def bundled(device):
    return device is None or device.startswith('pieusb:')


def features(device):
    """What the device can do beyond a colour scan."""
    return {'infrared': bundled(device), 'multi_exposure': bundled(device)}


def model(device):
    return models.get(device) or device.split(':')[0]


def environment(system=False):
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    if system:
        return env
    env['SANE_CONFIG_DIR'] = str(ROOT / 'sane')
    env['LD_LIBRARY_PATH'] = str(ROOT / 'driver')
    # From level 5 on the driver logs the exposure settings it sent to the scanner (see telemetry()).
    env['SANE_DEBUG_PIEUSB'] = '5'
    return env


# The patched driver logs how much of the image the scanner has captured; scanimage
# --progress then reports the transfer to the computer.
PROGRESS = re.compile(rb'NEGATIVSTUDIO acquisition ([0-9]+)\n|Progress:\s*([0-9]+(?:\.[0-9]+)?)%')


def _failed(log):
    lines = log.strip().splitlines()
    return ScannerError(lines[-1] if lines else 'scanimage fehlgeschlagen.')


def run(args, timeout, progress=None, system=None):
    """Run scanimage; return its stderr (driver log). `progress(fraction)` follows a scan as it runs.

    system: use the system's SANE backends; by default those of any device but a pieusb one.
    """
    if system is None:
        system = not bundled(args[args.index('-d') + 1] if '-d' in args else None)
    if progress is None:
        try:
            result = subprocess.run([SCANIMAGE, *args], env=environment(system), capture_output=True,
                                    text=True, errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ScannerHung(f'Scanner reagiert seit {timeout} s nicht.') from exc
        if result.returncode:
            raise _failed(result.stderr)
        return result.stderr + result.stdout
    deadline = time.monotonic() + timeout
    log = bytearray()
    last = None
    acquisition = False
    with subprocess.Popen([SCANIMAGE, *args], env=environment(system), stdout=subprocess.DEVNULL,
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
                acquisition = acquisition or acquired is not None
                # shortcut: capture and transfer count half each; measure their real durations to weight them
                if not acquisition:  # only the patched driver reports the capture; others report the transfer alone
                    value = float(transferred) / 100
                else:
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


def _devices(system):
    text = run(['--formatted-device-list=%d\t%v %m%n'], 30, system=system)
    return [line.split('\t', 1) for line in text.splitlines() if '\t' in line]


def find_device():
    """The SANE device name of a connected film scanner, or None; a Reflecta/PIE scanner first."""
    for system in (False, True):
        for device, name in _devices(system):
            backend = device.split(':')[0]
            if bundled(device) and not system:
                models[device] = name.strip()
                return device
            if backend in BACKENDS:
                try:
                    usable = BACKENDS[backend] == 'film' or transparency_source(parse_options(device_options(device)))
                except ScannerError:
                    usable = False
                if usable:  # a flatbed without film unit cannot scan film
                    models[device] = name.strip()
                    return device
    return None


def options(device, run=run):
    return run(['-d', device, '--mode=Color', '--depth=16', '--all-options', '--dont-scan'], 30)


_listed = {}


def device_options(device, source=None):
    """scanimage's option list of a system-SANE device; options can depend on the source, so it is set first."""
    key = (device, source)
    if key not in _listed:
        _listed[key] = run(['-d', device, *([f'--source={source}'] if source else []), '--all-options', '--dont-scan'], 30)
    return _listed[key]


def parse_options(text):
    """{option: [choices]} from scanimage --all-options; a range lo..hi gives [lo, hi] and a flag ['yes', 'no']."""
    result = {}
    for line in text.splitlines():
        match = re.match(r'\s+--([\w-]+)(.*)$', line)
        if not match:
            continue
        name, rest = match.groups()
        rest = re.sub(r'\s*\[[^\]]*\]\s*$', '', rest.strip())  # the current value
        if rest.startswith('[=('):
            result[name] = ['yes', 'no']
        elif '..' in rest:
            result[name] = [float(v) for v in re.findall(r'[0-9]+(?:\.[0-9]+)?', rest)[:2]]
        else:
            result[name] = [c.strip() for c in re.sub(r'(dpi|bit|mm|%|us)$', '', rest).split('|') if c.strip()]
    return result


def transparency_source(listed):
    """The source value that scans film (a film unit or transparency adapter), or None."""
    return next((c for c in listed.get('source', []) if re.search(r'transparen|film|tpu', c, re.I)), None)


def _resolution(listed, wanted):
    choices = listed.get('resolution', [])
    if len(choices) == 2 and isinstance(choices[0], float):
        return int(min(max(wanted, choices[0]), choices[1]))
    numbers = [int(float(c)) for c in choices if re.fullmatch(r'[0-9.]+', c)]
    if not numbers:
        raise ScannerError('Der Scanner meldet keine Auflösungen.')
    return min(numbers, key=lambda d: abs(d - wanted))


def generic_arguments(device, text, output, dpi):
    """scanimage arguments for a system-SANE film scan: linear 16-bit colour, no inversion or corrections.

    `text` is the device's option list; only options it lists are set, since names and values differ by backend.
    """
    listed = parse_options(text)
    args = ['-d', device]
    source = transparency_source(listed)
    if source:
        args.append(f'--source={source}')
    elif BACKENDS.get(device.split(':')[0]) != 'film':
        raise ScannerError('Der Scanner hat keine Filmeinheit.')
    if 'mode' in listed:
        mode = next((c for c in listed['mode'] if c.lower() == 'color'), None)
        if not mode:
            raise ScannerError('Der Scanner bietet keinen Farbmodus.')
        args.append(f'--mode={mode}')
    if 'depth' in listed:
        if '16' not in listed['depth']:
            raise ScannerError('Der Scanner liefert keine 16 Bit.')
        args.append('--depth=16')
    if BACKENDS.get(device.split(':')[0]) == 'flatbed':
        dpi = min(dpi, FLATBED_DPI)
    args.append(f'--resolution={_resolution(listed, dpi)}')
    # The development inverts negatives itself, so every film is scanned as a plain transparency.
    film = next((c for c in listed.get('film-type', []) if 'positive' in c.lower()), None)
    if film:
        args.append(f'--film-type={film}')
    for flag in ('negative', 'preview', 'infrared'):
        if flag in listed:
            args.append(f'--{flag}=no')
    return args + ['--format=pnm', '--progress', '--output-file', str(output)]


def _generic(device, output, dpi):
    source = transparency_source(parse_options(device_options(device)))
    return generic_arguments(device, device_options(device, source), output, dpi)


def dpi(args):
    return int(next(a for a in args if a.startswith('--resolution=')).split('=')[1])


def _arguments(device, output, dpi):
    return ['-d', device, '--mode=Color', '--depth=16', f'--resolution={dpi}',
            # The backend's own fast preview is fixed at 300 dpi; use a regular acquisition.
            '--preview=no', '--advance=no', '--clean-image=no', '--crop=None',
            '--calibration=from internal test', '--gain-adjust=* 1.0',
            '--format=pnm', '--progress', '--output-file', str(output)]


def preview_arguments(device, output):
    return _arguments(device, output, PREVIEW_DPI) if bundled(device) else _generic(device, output, PREVIEW_DPI)


def raw_arguments(device, output, infrared=False, manual=None, dpi=RAW_DPI):
    """One pass of a raw scan: the RGBI reference pass, or a Color pass with manual exposure."""
    if not bundled(device):
        if infrared or manual is not None:
            raise ValueError('Infrarot und Mehrfachbelichtung nur mit Reflecta/PIE-Scannern.')
        return _generic(device, output, dpi)
    args = _arguments(device, output, dpi) + ['--shading-analysis=yes']
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
