"""Converting screen images for a wide-gamut monitor from its EDID."""
import unittest
from unittest import mock

import numpy as np

from proscan.gui import monitor

P3 = ((.680, .320), (.265, .690), (.150, .060), (.3127, .3290))


def edid(p):
    """The 10 chromaticity bytes of an EDID for primaries `p`, in a minimal 128-byte block."""
    v = [round(c * 1024) for xy in p for c in xy]
    data = bytearray(b'\x00\xff\xff\xff\xff\xff\xff\x00' + bytes(120))
    data[25] = (v[0] & 3) << 6 | (v[1] & 3) << 4 | (v[2] & 3) << 2 | (v[3] & 3)
    data[26] = (v[4] & 3) << 6 | (v[5] & 3) << 4 | (v[6] & 3) << 2 | (v[7] & 3)
    data[27:35] = bytes(x >> 2 for x in v)
    return bytes(data)


class MonitorTests(unittest.TestCase):
    def test_primaries_from_edid(self):
        np.testing.assert_allclose(monitor.primaries(edid(P3)), P3, atol=.001)

    def test_srgb_monitor_needs_no_conversion(self):
        np.testing.assert_allclose(monitor.matrix(monitor.SRGB), np.eye(3), atol=1e-9)

    def test_srgb_red_on_a_p3_monitor_is_less_saturated_and_grey_stays_grey(self):
        with mock.patch.object(monitor, 'connected_edid', lambda: edid(P3)):
            lookup = monitor._lookup()
        with mock.patch.object(monitor, 'LOOKUP', lookup):
            out = monitor.to_screen(np.array([[[255, 0, 0], [128, 128, 128], [255, 255, 255]]], np.uint8))
        red, grey, white = out[0].astype(int)
        self.assertTrue(225 < red[0] < 240 and 40 < red[1] < 70 and red[2] < 50, red)  # known: sRGB red ≈ P3 (234, 51, 35)
        self.assertLessEqual(np.ptp(grey), 1)
        self.assertTrue(np.all(white >= 254))


if __name__ == '__main__':
    unittest.main()
