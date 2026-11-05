from pathlib import Path
import sys
import time
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App
from engine import Sample


class FakeMouse:
    width, height = 1920, 1080
    def __init__(self):
        self.point = (500., 500.)
        self.events = []
        self.stop = False
    def position(self):
        return self.point
    def trusted(self):
        return True
    def emergency(self):
        return self.stop
    def move(self, x, y):
        self.point = (x, y)
        self.events.append(('move', x, y))
    def click(self):
        self.events.append(('click',))


class AppSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.mouse = FakeMouse()
        self.app = App(self.root, self.mouse)

    def tearDown(self):
        self.app.close()

    def send(self, t, w=(0., 0., 0.), a=(0., 0., 0.)):
        self.app.sample(time.monotonic(), Sample(t, w, a, (0., 0., -1.), 'left'))

    def arm(self):
        e = self.app.engine
        e.source, e.x_axis, e.y_axis = 'left', (1., 0., 0.), (0., 1., 0.)
        self.send(1)
        self.app.toggle()
        self.assertTrue(e.enabled)

    def test_diagnostics_do_not_emit_mouse_events(self):
        for i in range(30):
            self.send(i * .02, (1., 1., 0.), (.6, 0., 0.))
        self.assertEqual(self.mouse.events, [])

    def test_enable_requires_calibration(self):
        self.send(1)
        self.app.toggle()
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.mouse.events, [])

    def test_emergency_pauses_before_output(self):
        self.arm()
        self.mouse.stop = True
        self.send(1.02, (1., 0., 0.))
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.mouse.events, [])

    def test_late_queue_data_never_moves_pointer(self):
        self.arm()
        self.app.events.put((self.app.session, time.monotonic() - 1, Sample(1.02, (1., 0., 0.), (0., 0., 0.), (0., 0., -1.), 'left')))
        self.app.tick()
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.mouse.events, [])

    def test_tap_is_disabled_until_explicitly_checked(self):
        self.arm()
        for i in range(30):
            self.send(1 + i * .02, a=(.7 if i == 20 else .01, 0., 0.))
        self.assertFalse(any(event[0] == 'click' for event in self.mouse.events))

    def test_stopping_connection_clears_live_state(self):
        self.arm()
        self.app.disconnect()
        self.assertFalse(self.app.engine.enabled)
        self.assertFalse(self.app.fresh())


if __name__ == '__main__':
    unittest.main()
