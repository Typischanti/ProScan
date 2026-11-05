"""Infrared dust detection and conservative repair of small spots.

A dust mark must show as a local dark spot in infrared and as a small defect
in visible light at the same place; larger marks and film detail stay untouched.
"""
import cv2
import numpy as np


class InfraredRejected(ValueError):
    pass


def _local_median(plane):
    """Yield 32-row stripes with their 7x7 neighbourhood median."""
    h, w = plane.shape
    for y in range(0, h, 32):
        end = min(h, y + 32)
        top, bottom = max(0, y - 3), min(h, end + 3)
        block = np.asarray(plane[top:bottom], np.float32) / 65535
        padded = np.pad(block, ((max(0, 3 - y), max(0, end + 3 - h)), (3, 3)), mode='edge')
        median = np.median(np.lib.stride_tricks.sliding_window_view(padded, (7, 7)), axis=(-2, -1))
        yield y, end, block[y - top:end - top], median


def _small_spots(candidates, visible, ir_drop, red_drop):
    """Whole infrared spots of at most 60 pixels within a 10 x 10 box that also show in visible light.

    Judged on the whole spot: a hair is either repaired completely or left alone, never cut into dashes.
    Dust blocks infrared about as much as red; a dense highlight darkens infrared only by the cyan
    dye's slight crosstalk (a few percent of its red drop), so spots weaker than a third are kept.
    """
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.ascontiguousarray(candidates, dtype=np.uint8), connectivity=8, ltype=cv2.CV_32S)
    keep = ((stats[:, cv2.CC_STAT_AREA] <= 60) & (stats[:, cv2.CC_STAT_WIDTH] <= 10)
            & (stats[:, cv2.CC_STAT_HEIGHT] <= 10))
    seen = np.zeros(count, bool)
    seen[labels[visible]] = True
    keep &= seen
    flat = labels.ravel()
    ir_mean = np.bincount(flat, ir_drop.ravel(), count)
    red_mean = np.bincount(flat, red_drop.ravel(), count)
    keep &= ir_mean >= red_mean / 3
    keep[0] = False
    return keep[labels]


def dust_mask(reference, infrared):
    """Boolean mask of dust pixels in `reference` (the visible pass the infrared was taken with)."""
    if infrared.ndim != 2 or infrared.shape != reference.shape[:2]:
        raise InfraredRejected('Infrarotgröße passt nicht zur Referenz.')
    h, w = infrared.shape
    if min(h, w) < 32:
        raise InfraredRejected('Infrarotaufnahme zu klein.')
    sample = np.asarray(infrared[::max(1, h // 300), ::max(1, w // 300)], float) / 65535
    if np.median(sample) < .05 or np.mean((sample < .005) | (sample > .995)) > .1:
        raise InfraredRejected('Infrarotaufnahme zu dunkel oder zu stark gesättigt.')
    candidates = np.zeros((h, w), bool)
    visible = np.zeros((h, w), bool)
    # How much darker than its surroundings, in stops, in infrared and in red.
    ir_drop = np.zeros((h, w), np.float32)
    red_drop = np.zeros((h, w), np.float32)
    for y, end, block, median in _local_median(infrared):
        delta = median - block
        noise = float(np.median(np.abs(delta)))
        candidates[y:end] = (delta > np.maximum(.08 * median, max(.025, 6 * noise))) & (median > .06)
        ir_drop[y:end] = np.log2(np.maximum(median, 1e-4) / np.maximum(block, 1e-4))
    for y, end, block, median in _local_median(reference[..., 0]):
        visible[y:end] = abs(median - block) > .025
        red_drop[y:end] = np.log2(np.maximum(median, 1e-4) / np.maximum(block, 1e-4))
    candidates[:4] = candidates[-4:] = False
    candidates[:, :4] = candidates[:, -4:] = False
    count = int(candidates.sum())
    if count / (h * w) > .02:
        raise InfraredRejected('Zu viele Infrarotfehlstellen; Filmstruktur oder ungeeigneter Film vermutet.')
    if count == 0:
        return candidates, {'candidates': 0, 'shift_yx': [0, 0]}
    if count < 8:
        raise InfraredRejected('Zu wenige Staubmerkmale für die Zuordnungsprüfung.')
    # Infrared and visible light are read a little apart; find the offset that matches.
    scores = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            moved = np.roll(candidates, (dy, dx), (0, 1))
            scores.append((np.count_nonzero(moved & visible) / count, dy, dx))
    scores.sort(reverse=True)
    score, dy, dx = scores[0]
    # Spots are several pixels wide, so offsets next to the best one always score nearly as well;
    # the match is clear when it beats every offset two or more pixels away.
    distant = max(s for s, y, x in scores if abs(y - dy) > 1 or abs(x - dx) > 1)
    # Never guess an ambiguous offset or one at the search boundary.
    if score < .25 or abs(dy) == 2 or abs(dx) == 2 or score - distant < .1:
        raise InfraredRejected('Infrarot-Staubstellen lassen sich dem Bild nicht eindeutig zuordnen.')
    mask = _small_spots(np.roll(candidates, (dy, dx), (0, 1)), visible, np.roll(ir_drop, (dy, dx), (0, 1)), red_drop)
    # One pixel more all round: a speck's soft edge is below the thresholds and stayed as a faint ring.
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return mask, {'candidates': count, 'shift_yx': [dy, dx], 'alignment_match': score,
                  'selected_pixels': int(mask.sum())}


def repair(image, mask):
    """A copy of float32 RGB `image` with the masked pixels inpainted; nothing else changes."""
    output = np.array(image, np.float32)
    h = output.shape[0]
    for y in range(0, h, 64):
        end = min(h, y + 64)
        selected = mask[y:end]
        if not selected.any():
            continue
        # Context halo so stripe borders never cut a selected spot.
        top, bottom = max(0, y - 16), min(h, end + 16)
        local_mask = mask[top:bottom].astype(np.uint8)
        for c in range(3):
            plane = np.ascontiguousarray(image[top:bottom, :, c] / 65535, dtype=np.float32)
            values = cv2.inpaint(plane, local_mask, 3, cv2.INPAINT_NS)[y - top:end - top][selected] * 65535
            if not np.all(np.isfinite(values)):
                raise InfraredRejected('Staubreparatur lieferte ungültige Werte.')
            output[y:end, :, c][selected] = np.clip(values, plane.min() * 65535, plane.max() * 65535)
    return output
