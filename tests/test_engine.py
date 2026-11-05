import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Engine, Sample, TapDetector, calibration_axis


def sample(t, w=(0., 0., 0.), a=(0., 0., 0.), source='left'):
    return Sample(t, w, a, (0., 0., -1.), source)


def ready():
    engine = Engine()
    engine.source = 'left'
    engine.x_axis, engine.y_axis = (1., 0., 0.), (0., 1., 0.)
    engine.enabled = True
    return engine


class MotionTests(unittest.TestCase):
    def test_starts_disarmed(self):
        engine = Engine()
        for i in range(100):
            self.assertEqual(engine.process(sample(i * .02, (1., 0., 0.))), (0., 0., None))

    def test_directions_and_inversion(self):
        engine = ready()
        engine.process(sample(1))
        dx, dy, _ = engine.process(sample(1.02, (1., 1., 0.)))
        self.assertGreater(dx, 0)
        self.assertLess(dy, 0)
        engine.invert_x = engine.invert_y = True
        for i in range(1, 30):
            dx, dy, _ = engine.process(sample(1.02 + i * .02, (1., 1., 0.)))
        self.assertLess(dx, 0)
        self.assertGreater(dy, 0)

    def test_gap_disarms_and_never_auto_resumes(self):
        engine = ready()
        engine.process(sample(1))
        self.assertEqual(engine.process(sample(2, (1., 0., 0.))), (0., 0., None))
        self.assertFalse(engine.enabled)
        self.assertEqual(engine.process(sample(2.02, (1., 0., 0.))), (0., 0., None))

    def test_source_change_requires_calibration(self):
        engine = ready()
        engine.process(sample(1))
        engine.process(sample(1.02, source='right'))
        self.assertFalse(engine.enabled)
        self.assertFalse(engine.calibrated)

    def test_nan_and_bad_gravity_disarm(self):
        for bad in [sample(1, (math.nan, 0., 0.)), Sample(1, (0., 0., 0.), (0., 0., 0.), (0., 0., 0.), 'left')]:
            engine = ready()
            self.assertEqual(engine.process(bad), (0., 0., None))
            self.assertFalse(engine.enabled)

    def test_nonmonotonic_disarms(self):
        engine = ready()
        engine.process(sample(1))
        engine.process(sample(.99))
        self.assertFalse(engine.enabled)

    def test_velocity_is_bounded(self):
        engine = ready()
        engine.process(sample(1))
        dx, dy, _ = engine.process(sample(1.02, (50., 0., 0.)))
        self.assertLessEqual(abs(dx), 1800 * .021)

    def test_stillness_and_signed_axis_learning(self):
        engine = Engine()
        engine.calibrate_still([sample(i * .02, (.01, .02, 0.)) for i in range(50)])
        self.assertAlmostEqual(engine.bias[1], .02)
        right = [sample(2 + i * .02, (.31, .02, 0.)) for i in range(50)]
        engine.set_axis('x', right)
        up = [sample(4 + i * .02, (.01, -.28, 0.)) for i in range(50)]
        engine.set_axis('y', up)
        self.assertTrue(engine.calibrated)
        self.assertAlmostEqual(engine.y_axis[1], -1)

    def test_reject_axis_same_as_horizontal(self):
        engine = ready()
        with self.assertRaises(ValueError):
            engine.set_axis('y', [sample(2 + i * .02, (.3, 0., 0.)) for i in range(50)])

    def test_no_movement_cannot_calibrate(self):
        with self.assertRaises(ValueError):
            calibration_axis([sample(i * .02) for i in range(50)], (0., 0., 0.))

    def test_calibration_rejects_moving_and_interrupted(self):
        engine = Engine()
        with self.assertRaises(ValueError):
            engine.calibrate_still([sample(i * .02, (1., 0., 0.)) for i in range(50)])
        with self.assertRaises(ValueError):
            engine.calibrate_still([sample(i * .2) for i in range(50)])


class TapTests(unittest.TestCase):
    def feed(self, a_values, w=(0., 0., 0.), dt=.02):
        detector = TapDetector()
        return [detector.feed(sample(i * dt, w, (a, 0., 0.))) for i, a in enumerate(a_values)]

    def test_single_impulse_clicks_once(self):
        result = self.feed([.02] * 20 + [.6, .25, .03] + [.02] * 25)
        fired = [v for v in result if v is not None]
        self.assertEqual(len(fired), 1)
        self.assertAlmostEqual(fired[0], .4)

    def test_wave_and_sustained_pressure_do_not_click(self):
        for values, w in [([.02] * 20 + [.6] * 15 + [.02] * 20, (0., 0., 0.)),
                          ([.02] * 20 + [.6, .25, .03] + [.02] * 20, (2., 0., 0.))]:
            self.assertFalse(any(x is not None for x in self.feed(values, w)))

    def test_no_history_cannot_click(self):
        self.assertFalse(any(x is not None for x in self.feed([.8, .1, .02])))

    def test_same_detection_at_25_and_50_hz(self):
        for dt in (.02, .04):
            count = round(.4 / dt)
            result = self.feed([.02] * count + [.6, .03] + [.02] * count, dt=dt)
            self.assertEqual(len([x for x in result if x is not None]), 1)


if __name__ == '__main__':
    unittest.main()
