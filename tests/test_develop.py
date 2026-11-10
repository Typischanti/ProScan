"""Development checks on synthetic negatives and slides of known exposure."""
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

from proscan import develop, flat, frames
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


class AutoLockTests(unittest.TestCase):
    def test_locked_frame_takes_the_auto_correction_of_its_source(self):
        with tempfile.TemporaryDirectory() as d:
            roll = Roll.create({'name': 'R', 'film_type': 'colour_negative'}, root=Path(d))
            for n, light in ((1, 1.), (2, .6)):  # the same scene, the second a little denser
                roll.frame_dir(n).mkdir(parents=True)
                np.save(roll.frame_dir(n) / 'rohscan.npy', negative(scene()) * light)
                roll.frames.append({'number': n, 'crop': dict(INNER), 'correction': dict(develop.AUTO)})
            own = frames.params(roll, 2, frames.film_base(roll, 2)[0])
            roll.frames[1]['auto_from'] = 1
            locked = frames.params(roll, 2, frames.film_base(roll, 2)[0])
            self.assertEqual(locked, frames.params(roll, 1, frames.film_base(roll, 1)[0]))
            self.assertNotEqual(locked, own)


class ColourTests(unittest.TestCase):
    def roll(self, d, scenes):
        roll = Roll.create({'name': 'R', 'film_type': 'colour_negative'}, root=Path(d))
        for n, s in enumerate(scenes, 1):
            roll.frame_dir(n).mkdir(parents=True)
            np.save(roll.frame_dir(n) / 'rohscan.npy', negative(s))
            roll.frames.append({'number': n, 'crop': dict(INNER), 'correction': dict(develop.AUTO)})
        return roll

    def grey(self, roll, n, x, y):
        """Colour spread (max/min) of the developed frame n at scan point (x, y)."""
        image = frames.view(roll, n)
        base = frames.film_base(roll, n)[0]
        out = develop.render(image, 'colour_negative', base, frames.params(roll, n, base), develop.AUTO, roll.settings['look'])
        h, w = out.shape[:2]
        pixel = out[int(y * h), int(x * w)]
        return pixel.max() / pixel.min()

    def test_scan_point_finds_the_spot_through_crop_angle_and_turn(self):
        shape = (200, 300)
        spot = np.zeros(shape, np.float32)
        spot[70:74, 180:184] = 1
        for turn in (0, 90, 180, 270):
            crop = {**INNER, 'angle': 2., 'turn': turn}
            shown = develop.apply_crop(spot, crop)
            y, x = np.unravel_index(np.argmax(shown), shown.shape)
            at = (x + .5) / shown.shape[1], (y + .5) / shown.shape[0]
            sx, sy = develop.scan_point(crop, shape, *at)
            np.testing.assert_allclose(develop.frame_point(crop, shape, sx, sy), at, atol=1e-6)  # and back, for its mark
            self.assertAlmostEqual(sx * 300, 182, delta=3, msg=turn)
            self.assertAlmostEqual(sy * 200, 72, delta=3, msg=turn)

    def test_neutral_spot_takes_out_the_cast(self):
        for look in ('frontier', 'filmdata'):
            picked = []
            for tint in ([1., .8, .6], [1., 1., 1.]):  # a warm light over everything; the ramp's grey is cast too
                with tempfile.TemporaryDirectory() as d:
                    roll = self.roll(d, [scene() * tint])
                    roll.settings['look'] = look
                    before = self.grey(roll, 1, .6, .75)
                    roll.frames[0]['neutral'] = [.6, .75]
                    picked.append(self.grey(roll, 1, .6, .75))
                    self.assertLessEqual(picked[-1], before + 1e-3, look)
            # As grey as the look prints a grey shot without a cast (its warm shadows are the look's own).
            self.assertAlmostEqual(picked[0], picked[1], delta=.01, msg=look)
            self.assertLess(picked[0], 1.08, look)

    def test_film_profile_learned_from_grey_points(self):
        # A film whose red layer is flatter and blue steeper: greys at five brightnesses, one per frame.
        film = np.array([.8, 1., 1.2])
        greys = [BASE * np.exp2(-film * stops * develop.FILM_GAMMA['colour_negative'] @ np.linalg.inv(develop.DYE_SEPARATION).T)
                 for stops in (1., 2., 3., 4., 5.)]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(frames, 'PROFILES', Path(d) / 'filmprofile.json'):
            roll = Roll.create({'name': 'R', 'film_type': 'colour_negative', 'film_stock': 'Neu 400'}, root=Path(d))
            for n, grey in enumerate(greys, 1):
                raw = np.full((200, 300, 3), grey, np.float32)
                roll.frame_dir(n).mkdir(parents=True)
                np.save(roll.frame_dir(n) / 'rohscan.npy', raw)
                roll.frames.append({'number': n, 'crop': dict(INNER), 'correction': dict(develop.AUTO),
                                    'film_base': {'measured': list(BASE), 'from': None, 'flat': flat.stamp()}})
            for frame in roll.frames[:3]:
                frame['neutral'] = [.5, .5]
            self.assertIsNone(frames.gain(roll))                 # three grey points are too few
            self.assertFalse(frames.remember_gain(roll))
            for frame in roll.frames[3:]:
                frame['neutral'] = [.5, .5]
            np.testing.assert_allclose(frames.gain(roll), 1 / film, rtol=.02)
            self.assertEqual(frames.profile(roll)[0], 'learned')
            self.assertTrue(frames.remember_gain(roll))
            self.assertFalse(frames.remember_gain(roll))         # kept already
            later = Roll.create({'name': 'S', 'film_type': 'colour_negative', 'film_stock': 'neu 400'}, root=Path(d))
            np.testing.assert_allclose(frames.gain(later), 1 / film, rtol=.02)  # the next roll of the stock has it
            self.assertEqual(frames.profile(later)[0], 'kept')
            frames.forget_gain(later)
            self.assertEqual(frames.profile(later), (None, None))
            frames.remember_gain(roll)
            other = Roll.create({'name': 'T', 'film_type': 'colour_negative', 'film_stock': 'Kodak Portra 800'}, root=Path(d))
            self.assertEqual(frames.profile(other), ('builtin', develop.FILM_GAINS['portra800']))

    def test_several_grey_points_on_one_frame(self):
        with tempfile.TemporaryDirectory() as d:
            roll = self.roll(d, [scene() * [1., .8, .6]])
            roll.frames[0]['neutral'] = [.6, .75]              # as kept before a frame could have several
            one = frames.params(roll, 1, frames.film_base(roll, 1)[0])
            roll.frames[0]['neutral'] = [[.6, .75]]
            self.assertEqual(frames.params(roll, 1, frames.film_base(roll, 1)[0]), one)
            roll.frames[0]['neutral'] = [[.6, .75], [.3, .75]]  # a lighter and a darker grey of the ramp
            self.assertEqual(len(frames.grey_stops(roll, 1)), 2)
            self.assertLess(self.grey(roll, 1, .6, .75), 1.08)
            self.assertLess(self.grey(roll, 1, .45, .75), 1.08)

    def test_colours_from_another_frame_with_own_brightness(self):
        with tempfile.TemporaryDirectory() as d:
            roll = self.roll(d, [scene() * [1., .8, .6], scene() * .5])
            roll.frames[0]['neutral'] = [.6, .75]
            base = frames.film_base(roll, 2)[0]
            own = frames.params(roll, 2, base)
            roll.frames[1]['colour_from'] = 1
            taken, source = frames.params(roll, 2, base), frames.params(roll, 1, frames.film_base(roll, 1)[0])
            np.testing.assert_allclose(np.diff(taken['black']), np.diff(source['black']), atol=1e-6)
            self.assertAlmostEqual(np.mean(taken['black']), np.mean(own['black']), places=5)
            self.assertEqual(frames.params(roll, 2, base, colour_from=2), own)  # its own colours while choosing it


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
        self.assertEqual(more.dtype, np.float32)  # float64 would make it twice as slow

    def test_film_stock_channel_contrast(self):
        self.assertEqual(develop.film_gain('Kodak Portra 800'), develop.FILM_GAINS['portra800'])
        self.assertEqual(develop.film_gain('portra800'), develop.FILM_GAINS['portra800'])
        self.assertIsNone(develop.film_gain('Kodak Portra 400'))
        self.assertEqual(develop.film_gain('Cinestill 400D'), develop.FILM_GAINS['cinestill400d'])
        self.assertIsNone(develop.film_gain(None))
        # Green with 17 % more contrast than red, as Portra 800 scans: the gain prints its greys grey again.
        raw = BASE * np.exp2(-np.array([1., 1.17, .88]) * np.linspace(0, 4, 50)[:, None, None] * develop.FILM_GAMMA['colour_negative']
                             @ np.linalg.inv(develop.DYE_SEPARATION).T)
        raw = np.repeat(raw, 4, axis=1).astype(np.float32)
        cast = lambda gain: np.ptp(develop.render(raw, 'colour_negative', BASE, develop.analyse(raw, 'colour_negative', BASE, 'faithful', gain=gain),
                                                  develop.AUTO, 'faithful')[20:40], axis=-1).mean()
        self.assertLess(cast((1, 1 / 1.17, 1 / .88)), cast(None) / 3)

    def test_developed_in_bands_as_in_one_piece(self):
        raw = np.repeat(self.raw, 3, axis=0)  # tall enough to be split across cores
        c = {**develop.AUTO, 'F': 2, 'Ch': 3}
        params = develop.analyse(raw, 'colour_negative', BASE, 'frontier')
        np.testing.assert_array_equal(develop.render(raw, 'colour_negative', BASE, params, c),
                                      develop._render(raw, 'colour_negative', BASE, params, c, 'frontier'))

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
