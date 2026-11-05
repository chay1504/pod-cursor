"""Case Mouse: real IMU samples -> relative movement and impulse tap detection.

Units: monotonic seconds, rotation rad/s, acceleration/gravity in g.
No hardware, UI, filesystem or mouse side effects in this module.
"""
from collections import deque
from dataclasses import dataclass
import math


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(v):
    return math.sqrt(dot(v, v))


def unit(v):
    length = norm(v)
    if length < 1e-8:
        raise ValueError('Movement was too small. Try calibration again.')
    return tuple(x / length for x in v)


@dataclass(frozen=True)
class Sample:
    t: float
    gyro: tuple
    accel: tuple
    gravity: tuple
    source: str = 'unknown'

    def valid(self):
        values = (self.t, *self.gyro, *self.accel, *self.gravity)
        return (len(self.gyro) == len(self.accel) == len(self.gravity) == 3
                and all(math.isfinite(x) for x in values)
                and norm(self.gyro) < 80 and norm(self.accel) < 30
                and .5 < norm(self.gravity) < 1.5)


def calibration_axis(samples, bias):
    if len(samples) < 10:
        raise ValueError('Too few sensor samples. Check the connection.')
    total = [0., 0., 0.]
    last = samples[0].t
    for sample in samples[1:]:
        dt = sample.t - last
        last = sample.t
        if not sample.valid() or not 0 < dt < .15:
            raise ValueError('Sensor stream was interrupted; retry calibration.')
        for i in range(3):
            total[i] += (sample.gyro[i] - bias[i]) * dt
    if not .12 < norm(total) < 2.5:
        raise ValueError('Turn about 15–45 degrees in ONE direction; do not turn back during recording.')
    return unit(total)


class TapDetector:
    """Quiet -> sharp impulse -> quick decay. Time based, not fixed sample rate."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.history = deque()
        self.pending = None
        self.last_fire = -math.inf

    def feed(self, sample):
        t, a, w = sample.t, norm(sample.accel), norm(sample.gyro)
        if self.history and not 0 < t - self.history[-1].t <= .15:
            self.reset()
        fired = None
        if self.pending:
            onset, peak = self.pending
            if t - onset > .12 or a > 4:
                self.pending = None
            elif t - onset >= .02 and a < peak * .45:
                fired, self.last_fire, self.pending = onset, t, None
            elif a > peak:
                self.pending = onset, a
        if not self.pending and fired is None and t - self.last_fire > .3 and self.history:
            quiet = [s for s in self.history if .02 <= t - s.t <= .18]
            previous = self.history[-1]
            quiet_span = t - self.history[0].t
            jerk = norm(tuple(x - y for x, y in zip(sample.accel, previous.accel)))
            if (quiet_span >= .14 and quiet and .25 <= a <= 4 and jerk >= .2
                    and w < 2 and max(norm(s.accel) for s in quiet) < .18
                    and max(norm(s.gyro) for s in quiet) < 1.2):
                self.pending = t, a
        self.history.append(sample)
        while self.history and t - self.history[0].t > .22:
            self.history.popleft()
        return fired


class Engine:
    def __init__(self):
        self.bias = (0., 0., 0.)
        self.x_axis = self.y_axis = None
        self.source = None
        self.enabled = False
        self.clicks = False
        self.gain = 900.
        self.invert_x = self.invert_y = False
        self.last = None
        self.velocity = (0., 0.)
        self.tap = TapDetector()
        self.freeze_until = -math.inf

    @property
    def calibrated(self):
        return self.x_axis is not None and self.y_axis is not None

    def pause(self):
        self.enabled = False
        self.last = None
        self.velocity = (0., 0.)
        self.tap.reset()
        self.freeze_until = -math.inf

    def calibrate_still(self, samples):
        if len(samples) < 15 or samples[-1].t - samples[0].t < .5:
            raise ValueError('Need at least half a second of uninterrupted data.')
        if any(not s.valid() or norm(s.gyro) > .2 or norm(s.accel) > .15 for s in samples):
            raise ValueError('Hold the case steady and try again.')
        if len({s.source for s in samples}) != 1:
            raise ValueError('Sensor changed earbuds; retry calibration.')
        if any(not 0 < b.t - a.t <= .15 for a, b in zip(samples, samples[1:])):
            raise ValueError('Sensor stream interrupted; retry calibration.')
        self.pause()
        self.source = samples[-1].source
        self.bias = tuple(sum(s.gyro[i] for s in samples) / len(samples) for i in range(3))
        self.x_axis = self.y_axis = None

    def set_axis(self, name, samples):
        if self.source is None or any(s.source != self.source for s in samples):
            raise ValueError('Hold-still calibration is required for this sensor.')
        axis = calibration_axis(samples, self.bias)
        if name == 'x':
            self.x_axis, self.y_axis = axis, None
        else:
            if self.x_axis is None:
                raise ValueError('Calibrate RIGHT first.')
            if abs(dot(axis, self.x_axis)) > .55:
                raise ValueError('UP movement matched RIGHT. Tilt the front upward instead of turning sideways.')
            self.y_axis = unit(tuple(a - dot(axis, self.x_axis) * x for a, x in zip(axis, self.x_axis)))
        self.pause()

    def process(self, sample):
        """Return (dx, dy, tap_onset_or_None); disarm on stale/invalid/source change."""
        if not sample.valid():
            self.pause()
            return 0., 0., None
        if self.source is not None and sample.source != self.source:
            self.x_axis = self.y_axis = None
            self.source = None
            self.pause()
            return 0., 0., None
        previous = self.last
        self.last = sample.t
        if previous is None:
            return 0., 0., None
        dt = sample.t - previous
        if not 0 < dt <= .15:
            self.pause()
            return 0., 0., None
        if not self.enabled or not self.calibrated:
            return 0., 0., None
        tap = self.tap.feed(sample) if self.clicks else None
        if tap is not None:
            self.freeze_until = sample.t + .15
        if self.tap.pending or sample.t < self.freeze_until:
            self.velocity = (0., 0.)
            return 0., 0., tap
        w = tuple(v - b for v, b in zip(sample.gyro, self.bias))
        rates = (dot(w, self.x_axis), -dot(w, self.y_axis))
        target = []
        for rate, inverted in zip(rates, (self.invert_x, self.invert_y)):
            effective = math.copysign(max(0., abs(rate) - .03), rate)
            speed = effective * self.gain
            target.append(max(-1800., min(1800., -speed if inverted else speed)))
        alpha = 1 - math.exp(-dt / .035)
        self.velocity = tuple(a + alpha * (b - a) for a, b in zip(self.velocity, target))
        return self.velocity[0] * dt, self.velocity[1] * dt, tap
