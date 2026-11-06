"""Development checks on synthetic negatives and slides of known exposure."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from proscan import develop, frames
from proscan.roll import Roll

BASE = np.array([.30, .14, .07]) * 65535  # orange mask, as measured on Kodak Gold 200


def negative(scene, clear_edges=True):
    """Scanner counts of a colour negative of `scene` (linear, 0.02..1): density = gamma * log exposure.

    With clear_edges, unexposed film shows left and right; without, the picture
    reaches the edges, textured like a real photograph.
    """
    scene = scene.copy()
    w = scene.shape[1]
    if not clear_edges:
        texture = np.random.default_rng(3).uniform(.05, .6, scene.shape[:2] + (1,))
        scene[:, :w // 20] = texture[:, :w // 20]
        scene[:, -w // 20:] = texture[:, -w // 20:]
    t = BASE * (scene / .02) ** -develop.FILM_GAMMA['colour_negative']
    if clear_edges:
        t[:, :w // 30] = BASE
        t[:, -w // 30:] = BASE
    return t.astype(np.float32)


def scene(h=200, w=300):
    """A grey ramp with a red, a green and a blue patch, linear 0.02..1."""
    s = np.repeat(np.repeat(np.geomspace(.02, 1, w)[None, :, None], h, 0), 3, 2)
    s[20:60, 60:100] = [.5, .08, .08]
    s[20:60, 130:170] = [.08, .4, .08]
    s[20:60, 200:240] = [.08, .08, .5]
    return s


FULL = {'x': 0., 'y': 0., 'w': 1., 'h': 1., 'angle': 0.}
INNER = {'x': .05, 'y': 0., 'w': .9, 'h': 1., 'angle': 0.}


def developed(raw, film_type='colour_negative', correction=develop.AUTO, look='frontier', base=None):
    cropped = develop.apply_crop(raw, INNER)
    base = base if base is not None or film_type == 'colour_positive' else develop.measure_film_base(raw)
    return develop.render(cropped, film_type, base, develop.analyse(cropped, film_type, base, look), correction, look)


class FilmBaseTests(unittest.TestCase):
    def test_measured_from_the_clear_film_at_the_edges(self):
        np.testing.assert_allclose(develop.measure_film_base(negative(scene())), BASE, rtol=.01)

    def test_none_without_clear_film(self):
        self.assertIsNone(develop.measure_film_base(negative(scene(), clear_edges=False)))

    def test_stray_light_is_not_taken_for_film_base(self):
        raw = negative(scene())
        raw[:, :4] = 60000  # light past the film edge
        np.testing.assert_allclose(develop.measure_film_base(raw), BASE, rtol=.01)

    def test_frames_without_clear_film_borrow_the_nearest_earlier_one(self):
        with tempfile.TemporaryDirectory() as d:
            roll = Roll.create({'name': 'R', 'film_type': 'colour_negative'}, root=Path(d))
            for n, edges in ((1, False), (2, True), (3, False), (4, True)):
                roll.frame_dir(n).mkdir(parents=True)
                np.save(roll.frame_dir(n) / 'rohscan.npy', negative(scene(), clear_edges=edges) * (1 + n / 100))
                roll.frames.append({'number': n, 'crop': dict(INNER), 'correction': dict(develop.AUTO)})
            kinds = [frames.film_base(roll, n)[1:] for n in (1, 2, 3, 4)]
            self.assertEqual(kinds, [(2, 'borrowed'), (2, 'own'), (2, 'borrowed'), (4, 'own')])
            roll.frames[2]['film_base']['from'] = 4
            self.assertEqual(frames.film_base(roll, 3)[1:], (4, 'chosen'))


class NegativeTests(unittest.TestCase):
    def setUp(self):
        self.raw = negative(scene())

    def test_prints_like_paper_black_to_white_and_neutral(self):
        y = developed(self.raw)
        ramp = y[150]
        self.assertLess(ramp[2].max(), .1)       # the scene's darkest grey prints near black
        self.assertGreater(ramp[-3].min(), .9)   # its brightest near white
        self.assertTrue(np.all(np.diff(ramp @ develop.LUMA) >= -1e-4))
        mid = ramp[len(ramp) // 2]
        self.assertLess(np.ptp(mid), .06)        # greys stay grey (Frontier look adds only a little warmth)

    def test_colours_come_out_as_shot(self):
        y = developed(self.raw)
        red, green, blue = y[40, 70], y[40, 125], y[40, 195]
        self.assertEqual([int(np.argmax(c)) for c in (red, green, blue)], [0, 1, 2])

    def test_keys(self):
        auto = developed(self.raw)
        darker = developed(self.raw, correction={'D': 6})
        self.assertLess(float((darker @ develop.LUMA).mean()), float((auto @ develop.LUMA).mean()) - .03)
        cyan = developed(self.raw, correction={'C': 6})
        self.assertLess(cyan[..., 0].mean(), auto[..., 0].mean() - .01)
        np.testing.assert_allclose(cyan[..., 1].mean(), auto[..., 1].mean(), atol=.01)
        harder = developed(self.raw, correction={'G': 3})
        self.assertGreater((harder @ develop.LUMA).std(), (auto @ develop.LUMA).std())

    def test_tone_range_keys(self):
        auto = developed(self.raw)
        dark, light = np.s_[150, 10:60], np.s_[150, 220:260]
        shadows = developed(self.raw, correction={'Cs': 6})
        self.assertLess(shadows[dark][..., 0].mean(), auto[dark][..., 0].mean() - .01)
        self.assertLess(abs(shadows[light][..., 0].mean() - auto[light][..., 0].mean()),
                        abs(shadows[dark][..., 0].mean() - auto[dark][..., 0].mean()) / 3)
        highlights = developed(self.raw, correction={'Yh': 6})
        self.assertLess(highlights[light][..., 2].mean(), auto[light][..., 2].mean() - .01)
        self.assertLess(abs(highlights[dark][..., 2].mean() - auto[dark][..., 2].mean()), .005)
        # The same step in all three ranges is the whole-frame key.
        np.testing.assert_allclose(developed(self.raw, correction={'Mh': 4, 'Mm': 4, 'Ms': 4}),
                                   developed(self.raw, correction={'M': 4}), atol=1e-4)

    def test_midtone_brightness_keeps_black_and_white(self):
        auto, lighter = developed(self.raw), developed(self.raw, correction={'H': 6})
        luma = lambda y: y[150] @ develop.LUMA
        self.assertGreater(luma(lighter)[len(luma(auto)) // 2], luma(auto)[len(luma(auto)) // 2] + .05)
        self.assertAlmostEqual(luma(lighter)[2], luma(auto)[2], delta=.02)
        self.assertAlmostEqual(luma(lighter)[-3], luma(auto)[-3], delta=.02)

    def test_scenes(self):
        def scene(name):
            cropped = develop.apply_crop(self.raw, INNER)
            base = develop.measure_film_base(self.raw)
            return develop.render(cropped, 'colour_negative', base, develop.analyse(cropped, 'colour_negative', base, 'frontier', name),
                                  {'scene': name}, 'frontier')
        mean = lambda y: float((y @ develop.LUMA).mean())
        saturation = lambda y: float(np.mean(y.max(axis=2) - y.min(axis=2)))
        standard = scene('standard')
        self.assertGreater(mean(scene('snow')), mean(standard) + .03)
        self.assertLess(mean(scene('night')), mean(standard) - .03)
        self.assertLess(saturation(scene('portrait')), saturation(standard))
        self.assertGreater(saturation(scene('landscape')), saturation(standard))
        indoor = scene('indoor')
        self.assertLess(indoor[..., 0].mean() - indoor[..., 2].mean(), standard[..., 0].mean() - standard[..., 2].mean())

    def test_subtractive_saturation(self):
        y = develop.srgb_decode  # only for readability below
        patches = np.array([[[.8, .25, .2], [.5, .5, .5], [.55, .5, .45]]], np.float32)  # red, grey, a muted warm tone
        more, less = develop.subtractive_saturation(patches, 1.48), develop.subtractive_saturation(patches, .52)
        chroma = lambda c: float(c.max() - c.min())
        luma = lambda c: float(y(c) @ develop.LUMA)
        red, grey = patches[0, 0], patches[0, 1]
        self.assertGreater(chroma(more[0, 0]), chroma(red))
        self.assertLess(luma(more[0, 0]), luma(red))       # more dye: deeper and darker, unlike additive saturation
        self.assertGreater(luma(less[0, 0]), luma(red))
        self.assertAlmostEqual(more[0, 0, 0], red[0], 3)   # the least dense channel (the colour's neutral part) stays
        np.testing.assert_allclose(more[0, 1], grey, atol=1e-5)
        vivid = develop.subtractive_saturation(patches, 1, 6)
        gain = lambda before, after: chroma(after) / chroma(before)
        self.assertGreater(gain(patches[0, 2], vivid[0, 2]), gain(red, vivid[0, 0]))  # muted colours gain most

    def test_saturation_keys_leave_black_and_white_alone(self):
        np.testing.assert_allclose(developed(self.raw, 'bw_negative', correction={'F': 6, 'V': 6}),
                                   developed(self.raw, 'bw_negative'), atol=1e-6)

    def test_roll_balance_removes_the_films_cast(self):
        # The same blue-short cast on every frame of a roll (as from film, mask or scanner).
        cast = negative(scene()) * np.array([1., 1., 1.25], np.float32)
        lv = develop.levels(cast)
        balance = develop.roll_balance([lv, lv, lv], [BASE, BASE, BASE], 'colour_negative')
        cropped = develop.apply_crop(cast, INNER)
        grey = lambda roll: develop.render(cropped, 'colour_negative', BASE,
                                           develop.analyse(cropped, 'colour_negative', BASE, 'frontier', roll=roll))[150, 135]
        self.assertLess(np.ptp(grey(balance)), np.ptp(grey(None)))  # the mid grey is more neutral with the roll's cast

    def test_faithful_is_gentler_than_frontier(self):
        frontier, faithful = developed(self.raw), developed(self.raw, look='faithful')
        saturation = lambda y: float(np.mean(y.max(axis=2) - y.min(axis=2)))
        self.assertGreater(saturation(frontier), saturation(faithful))

    def test_black_and_white_is_grey(self):
        y = developed(self.raw, 'bw_negative')
        np.testing.assert_allclose(y[..., 0], y[..., 2], atol=1e-6)


class PositiveTests(unittest.TestCase):
    def test_faithful_slide_keeps_its_colours(self):
        s = scene()
        raw = (s * .9 * 65535).astype(np.float32)
        y = developed(raw, 'colour_positive', look='faithful')
        linear = develop.srgb_decode(y)
        red = linear[40, 70 - 15]
        self.assertAlmostEqual(red[0] / red[1], .5 / .08, delta=.6)  # the slide's own colour ratio
        grey = linear[150, 150]
        self.assertLess(np.ptp(grey) / grey.mean(), .02)


if __name__ == '__main__':
    unittest.main()
