"""The look 'filmdata': film stock data from scan to print."""
import unittest

import numpy as np

from proscan import develop, filmdata


def scan_of(key, log_exposure):
    """Scanned density above film base of a film exposed with `log_exposure` (n, 3): the forward model."""
    dye, base, curve = filmdata._film(key)
    c = np.stack([np.interp(log_exposure[:, k], filmdata.LOG_E, curve[:, k]) for k in range(3)], -1)
    bands = np.exp(-.5 * ((filmdata.W[:, None] - np.asarray(filmdata.SCANNER['centre'])) / np.asarray(filmdata.SCANNER['width'])) ** 2)
    weights = bands * 10 ** -base[:, None]
    weights /= weights.sum(0)
    return -np.log10(10 ** -(c @ dye.T) @ weights)


class FilmDataTests(unittest.TestCase):
    def test_film_stock_from_its_name(self):
        self.assertEqual(filmdata.stock('Kodak Portra 800'), 'kodak_portra_800')
        self.assertEqual(filmdata.stock('Fujicolor C200'), 'fujifilm_c200')
        self.assertEqual(filmdata.stock('Kodak UltraMax 400'), 'kodak_ultramax_400')
        self.assertEqual(filmdata.stock(''), filmdata.DEFAULT)

    def test_scan_back_to_the_light_in_the_camera(self):
        for key in filmdata.DATA['films']:
            grey = np.repeat(np.linspace(-1, 1.25, 10)[:, None], 3, 1)  # a scene: 3 stops under to 4 over mid grey
            np.testing.assert_allclose(filmdata.lookup(filmdata.exposure_table(key), filmdata.D_GRID, scan_of(key, grey)), grey,
                                       atol=.05, err_msg=key)  # a sixth of a stop

    def test_grey_prints_grey(self):
        for key in ('kodak_gold_200', 'kodak_portra_800', 'fujifilm_c200'):
            rgb = filmdata.lookup(filmdata.print_table(key), filmdata.E_GRID, np.repeat(np.linspace(0, 1.2, 7)[:, None], 3, 1))
            # Mid grey to highlights neutral within 8 %; the paper's deepest blacks are a little cool, as real Endura's.
            self.assertLess(float((rgb.max(1) / rgb.min(1)).max()), 1.08, key)
            self.assertTrue(np.all(np.diff(rgb.mean(1)) > 0))                  # more light, lighter print

    def test_develops_a_negative(self):
        key = 'kodak_portra_800'
        light = np.repeat(np.linspace(-1, 1.5, 60)[:, None], 3, 1)
        base = np.array([.30, .14, .07]) * 65535
        raw = (base * 10 ** -scan_of(key, light))[:, None, :].repeat(80, 1).astype(np.float32)
        params = develop.analyse(raw, 'colour_negative', base, 'filmdata', stock='Kodak Portra 800')
        self.assertEqual(params['stock'], key)
        out = develop.render(raw, 'colour_negative', base, params, develop.AUTO, 'filmdata')
        self.assertTrue(np.all(np.diff(out.mean(2)[:, 0]) >= -1e-3))  # brighter scene, brighter print
        darker = develop.render(raw, 'colour_negative', base, params, {**develop.AUTO, 'D': 3}, 'filmdata')
        self.assertLess(darker.mean(), out.mean())
        bluer = develop.render(raw, 'colour_negative', base, params, {**develop.AUTO, 'Y': -3}, 'filmdata')
        self.assertGreater((bluer[..., 2] - out[..., 2]).mean(), 0)

    def test_other_film_types_get_the_faithful_look(self):
        raw = np.full((40, 40, 3), 20000, np.float32)
        params = develop.analyse(raw, 'bw_negative', [30000] * 3, 'filmdata')
        self.assertNotIn('stock', params)
        develop.render(raw, 'bw_negative', [30000] * 3, params, develop.AUTO, 'filmdata')


if __name__ == '__main__':
    unittest.main()
