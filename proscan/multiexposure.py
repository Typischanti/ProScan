"""Multi-exposure: a second, longer pass merged into the reference pass.

Measured on the CrystalScan 7200: longer exposure times scale the signal
linearly, shorter ones do not (a planned 0.25x pass measured 0.52-0.97x).
So there is only one extra pass and it is always longer than the reference.
"""
import cv2
import numpy as np

EV = 2  # the longer pass aims for 4x the reference exposure, within the scanner's limits


class ExposureMismatch(ValueError):
    pass


def longer_pass(reference, ranges, ev=EV):
    """Manual settings for the longer pass; infrared exposure stays unchanged."""
    if any(not low <= v <= high for v, (low, high) in zip(reference['exposure'], ranges)):
        raise ValueError('Referenzbelichtung liegt außerhalb der gemeldeten Grenzen.')
    exposure = [min(high, round(v * 2 ** ev)) if i < 3 else v
                for i, (v, (low, high)) in enumerate(zip(reference['exposure'], ranges))]
    ratios = [exposure[c] / reference['exposure'][c] for c in range(3)]
    if max(ratios) <= 1:
        raise ValueError('Belichtung ist bereits am Maximum des Scanners.')
    return {'settings': {**reference, 'exposure': exposure}, 'ratios': ratios}


def shifted_samples(image, ys, xs, dy, dx):
    """Bilinear samples in scanner count units; callers provide valid coordinates."""
    y = np.asarray(ys) + dy
    x = np.asarray(xs) + dx
    if float(dy).is_integer() and float(dx).is_integer():
        return image[np.ix_(y.astype(int), x.astype(int))].astype(np.float32)
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    y1 = np.minimum(y0 + 1, image.shape[0] - 1)
    x1 = np.minimum(x0 + 1, image.shape[1] - 1)
    fy = (y - y0).astype(np.float32)[:, None, None]
    fx = (x - x0).astype(np.float32)[None, :, None]
    a = image[np.ix_(y0, x0)].astype(np.float32)
    b = image[np.ix_(y0, x1)].astype(np.float32)
    c = image[np.ix_(y1, x0)].astype(np.float32)
    d = image[np.ix_(y1, x1)].astype(np.float32)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def refine_translation(reference, moving, channel, shift):
    """ECC on a central patch, translation only: never scale, shear or warp film grain.

    Returning the initial shift on non-convergence leaves validation to the caller.
    """
    h, w = reference.shape[:2]
    ph, pw = min(h, 768), min(w, 768)
    y, x = (h - ph) // 2, (w - pw) // 2
    a = np.asarray(reference[y:y + ph, x:x + pw, channel], np.float32) / 65535
    b = np.asarray(moving[y:y + ph, x:x + pw, channel], np.float32) / 65535
    mask = ((b > .025) & (b < .94)).astype(np.uint8) * 255
    warp = np.array([[1, 0, shift[1]], [0, 1, shift[0]]], np.float32)
    try:
        _, warp = cv2.findTransformECC(np.log(np.maximum(a, .001)), np.log(np.maximum(b, .001)), warp,
                                       cv2.MOTION_TRANSLATION,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), mask, 3)
    except cv2.error:
        return shift
    dy, dx = float(warp[1, 2]), float(warp[0, 2])
    if not np.isfinite([dy, dx]).all() or max(abs(dy - shift[0]), abs(dx - shift[1])) > .75:
        return shift
    # Don't interpolate exactly aligned scans because of optimizer noise.
    if max(abs(dy - round(dy)), abs(dx - round(dx))) < .03:
        return shift
    return dy, dx


def _correlation(a, b):
    a = np.log(a)
    b = np.log(b)
    a -= a.mean()
    b -= b.mean()
    aa, bb = float(np.dot(a, a)), float(np.dot(b, b))
    return aa, bb, (float(np.dot(a, b) / np.sqrt(aa * bb)) if aa and bb else 0.)


def alignment(reference, moving, ratios, max_shift=12):
    """Integer search plus guarded ECC refinement; rejects ambiguous matches.

    Returns ((dy, dx), report); report['valid_channels'] says which colour
    channels of `moving` responded to the longer exposure as expected.
    """
    if reference.shape != moving.shape:
        raise ValueError('Die Durchläufe haben verschiedene Bildgrößen.')
    h, w = reference.shape[:2]
    margin = max_shift + max(2, min(h, w) // 20)
    if min(h, w) <= 2 * margin + 12:
        raise ValueError('Bild zu klein für die sichere Ausrichtung.')
    step = max(1, int(np.ceil(max(h, w) / 220)))
    ys = np.arange(margin, h - margin, step)
    xs = np.arange(margin, w - margin, step)
    samples = reference[np.ix_(ys, xs)].astype(np.float32) / 65535
    # The channel with the largest usable overlap at the expected exposure.
    channel = max(range(3), key=lambda c: np.count_nonzero(
        (samples[..., c] > .025) & (samples[..., c] < min(.94, .94 / ratios[c]))))
    ref = samples[..., channel]
    valid_ref = (ref > .025) & (ref < .94)
    scores = []
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            other = moving[np.ix_(ys + dy, xs + dx)][..., channel].astype(np.float32) / 65535
            valid = valid_ref & (other > .025) & (other < .94)
            if np.count_nonzero(valid) < 100:
                continue
            aa, bb, score = _correlation(ref[valid], other[valid])
            if aa / valid.sum() < .002 or bb / valid.sum() < .002:
                continue
            scores.append((score, dy, dx))
    if not scores:
        raise ValueError('Zu wenig Bildstruktur für die Ausrichtung.')
    scores.sort(reverse=True)
    score, dy, dx = scores[0]
    distant = [s for s, y, x in scores[1:] if abs(y - dy) > 1 or abs(x - dx) > 1]
    coarse = (dy, dx)
    if score < .9999:
        sy, sx = refine_translation(reference, moving, channel, (dy, dx))
        other = shifted_samples(moving, ys, xs, sy, sx)[..., channel] / 65535
        valid = valid_ref & (other > .025) & (other < .94)
        if np.count_nonzero(valid) >= 100:
            refined = _correlation(ref[valid], other[valid])[2]
            if refined > score + 1e-5:
                score, dy, dx = refined, sy, sx
    if score < .97 or abs(dy) >= max_shift or abs(dx) >= max_shift or (distant and score - max(distant) < .0005):
        raise ValueError('Die Durchläufe lassen sich nicht sicher ausrichten.')
    # Verify the physical response, not just a successful option-setting command.
    shifted = shifted_samples(moving, ys, xs, dy, dx) / 65535
    measured, valid_channels, reasons = [], [], []
    for c in range(3):
        a, b = samples[..., c], shifted[..., c]
        # From 2 %: behind an orange mask blue reaches only about 7 % of full scale, and a 5 % floor
        # left a sliver of nearly flat, noisy values that never correlated.
        mask = (a > .02) & (a < .85) & (b > .02) & (b < .85)
        ratio, reason = None, None
        if np.count_nonzero(mask) < 100:
            reason = 'Zu wenig gemeinsame Mitteltöne zur Belichtungsprüfung.'
        else:
            ratio = float(np.median(b[mask] / a[mask]))
            xx, yy, correlation = _correlation(a[mask], b[mask])
            if abs(ratio / ratios[c] - 1) > .15:
                reason = f'Gemessene Helligkeit {ratio:.3f}x statt erwartet {ratios[c]:.3f}x.'
            elif min(xx, yy) / mask.sum() < .002 or correlation < .97:
                reason = 'Farbkanal stimmt räumlich nicht mit der Referenz überein.'
        measured.append(ratio)
        valid_channels.append(reason is None)
        reasons.append(reason)
    return (dy, dx), {'coarse_shift_yx': list(coarse), 'shift_yx': [dy, dx], 'correlation': score,
                      'measured_ratios': measured, 'valid_channels': valid_channels, 'channel_reasons': reasons}


def merge(reference, longer, ratios):
    """Merge the longer pass into the reference; returns (float32 linear RGB, report).

    Values are reference counts; clipped extremes are rejected and the longer
    exposure is favoured. Channels of the longer pass that failed the exposure
    check are not used. Uncovered edge pixels keep the reference.
    """
    ratios = np.asarray(ratios, np.float32)
    (dy, dx), report = alignment(reference, longer, ratios)
    usable = np.asarray(report['valid_channels'])
    if not usable.any():
        raise ExposureMismatch(' '.join(r for r in report['channel_reasons'] if r))
    h, w, _ = reference.shape
    output = np.empty((h, w, 3), np.float32)
    x0, x1 = max(0, int(np.ceil(-dx))), min(w, int(np.floor(w - 1 - dx)) + 1)
    for y in range(0, h, 64):
        end = min(h, y + 64)
        base = reference[y:end].astype(np.float32)
        value = base / 65535
        weight = np.clip((value - .002) / .048, 0, 1) * np.clip((.98 - value) / .08, 0, 1)
        total, weights = base * weight, weight.copy()
        y0, y1 = max(y, int(np.ceil(-dy))), min(end, int(np.floor(h - 1 - dy)) + 1)
        if x1 > x0 and y1 > y0:
            target = np.s_[y0 - y:y1 - y, x0:x1]
            counts = shifted_samples(longer, np.arange(y0, y1), np.arange(x0, x1), dy, dx)
            value = counts / 65535
            weight = np.clip((value - .002) / .048, 0, 1) * np.clip((.98 - value) / .08, 0, 1) * ratios * usable
            total[target] += counts / ratios * weight
            weights[target] += weight
        # Where every pass clipped, keep the reference value.
        output[y:end] = np.divide(total, weights, out=base, where=weights > 0)
    report['ratios'] = ratios.tolist()
    report['used_channels'] = ['RGB'[c] for c in range(3) if usable[c]]
    return output, report
