"""Case Mouse: handheld earbud-case sensor prototype. No camera/marker input."""
from collections import deque
import argparse
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

from engine import Engine, Sample, norm
from mouse_output import Mouse

ROOT = Path(__file__).resolve().parent


def sensor_worker(stop, emit, service):
    child = None
    try:
        if sys.platform == 'win32':
            from windows_aap import stream
            stream(stop, emit, service)
        elif sys.platform == 'darwin':
            helper = ROOT / 'native/CaseMotion.app/Contents/MacOS/CaseMotion'
            if not helper.is_file():
                raise RuntimeError('Mac motion helper is not built. Run bash Setup-Mac.command first.')
            child = subprocess.Popen([str(helper)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            def watch_stop():
                stop.wait()
                if child.poll() is None:
                    child.terminate()
            threading.Thread(target=watch_stop, daemon=True).start()
            for line in child.stdout:
                if stop.is_set():
                    break
                try:
                    value = json.loads(line)
                    if 'gyro' in value:
                        emit(Sample(float(value['t']), tuple(value['gyro']), tuple(value['accel']), tuple(value['gravity']), str(value['source'])))
                    else:
                        emit(value)
                except (ValueError, TypeError, KeyError):
                    emit({'status': line.strip()[:300]})
            if not stop.is_set():
                raise RuntimeError('Mac motion helper exited. Check Motion permission and audio output.')
        else:
            raise RuntimeError('This build supports Windows and macOS.')
    except Exception as exc:
        emit({'error': str(exc)})
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
        emit({'ended': True})


class App:
    def __init__(self, root, mouse=None):
        self.root, self.mouse = root, mouse or Mouse()
        self.engine = Engine()
        self.events = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.worker = None
        self.live = None
        self.rates = deque()
        self.history = deque(maxlen=100)
        self.capture = None
        self.cal_samples = []
        self.last_receive = 0.
        self.cursor = self.mouse.position()
        self.session = 0
        self.status = tk.StringVar(value='Not connected — start with sensor diagnostics')
        self.telemetry = tk.StringVar(value='No sensor samples received')
        self.guide = tk.StringVar(value='Earbuds stay in the OPEN case. Turn the case to point; tap it to click.')
        self.clicks = tk.BooleanVar(value=False)
        self.speed = tk.DoubleVar(value=900)
        self.invert_x, self.invert_y = tk.BooleanVar(), tk.BooleanVar()
        self.service = tk.StringVar(value='16')
        root.title('Case Mouse — sensor prototype')
        root.geometry('740x690')
        root.minsize(700, 640)
        shell = ttk.Frame(root, padding=24)
        shell.pack(fill='both', expand=True)
        ttk.Label(shell, text='Case Mouse', font=('Segoe UI', 25, 'bold')).pack(anchor='w')
        ttk.Label(shell, text='Real motion sensors • Experimental hardware support', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 18))
        ttk.Label(shell, textvariable=self.guide, wraplength=670).pack(anchor='w', pady=5)
        ttk.Label(shell, text='1. Connect earbuds and turn OFF Automatic Ear Detection.\n2. Keep both earbuds inside the open case; select them as sound output.\n3. Start diagnostics, then calibrate before enabling pointer control.', justify='left').pack(anchor='w', pady=10)
        row = ttk.Frame(shell)
        row.pack(fill='x', pady=7)
        ttk.Button(row, text='Start sensor diagnostics', command=self.connect).pack(side='left')
        ttk.Button(row, text='Stop connection', command=self.disconnect).pack(side='left', padx=8)
        if sys.platform == 'win32':
            ttk.Label(row, text='AAP service').pack(side='left', padx=(14, 4))
            ttk.Combobox(row, textvariable=self.service, values=('16', '14', '6'), width=4, state='readonly').pack(side='left')
        ttk.Label(shell, textvariable=self.status, wraplength=670, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=8)
        ttk.Label(shell, textvariable=self.telemetry, wraplength=670).pack(anchor='w')
        ttk.Separator(shell).pack(fill='x', pady=15)
        row = ttk.Frame(shell)
        row.pack(fill='x')
        for label, mode in [('1 · Hold still', 'still'), ('2 · Turn RIGHT', 'x'), ('3 · Tilt UP', 'y')]:
            ttk.Button(row, text=label, command=lambda m=mode: self.calibrate(m)).pack(side='left', padx=(0, 8))
        self.arm_button = ttk.Button(shell, text='Enable pointer control', command=self.toggle)
        self.arm_button.pack(anchor='w', pady=(14, 6))
        ttk.Checkbutton(shell, text='Enable tap-to-left-click (test movement first)', variable=self.clicks, command=self.settings).pack(anchor='w')
        row = ttk.Frame(shell)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Pointer speed').pack(side='left')
        ttk.Scale(row, from_=250, to=1800, variable=self.speed, command=lambda _: self.settings()).pack(side='left', fill='x', expand=True, padx=12)
        for label, value in [('Reverse left/right', self.invert_x), ('Reverse up/down', self.invert_y)]:
            ttk.Checkbutton(shell, text=label, variable=value, command=self.settings).pack(anchor='w')
        ttk.Label(shell, text='Emergency pause: Ctrl+Alt+Q (Mac: Control+Option+Q), or move your physical mouse to a main-screen corner.', wraplength=670).pack(anchor='w', pady=12)
        self.log = tk.Text(shell, height=5, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(15, self.tick)

    def note(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        if int(self.log.index('end-1c').split('.')[0]) > 100:
            self.log.delete('1.0', '20.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def settings(self):
        self.engine.clicks = self.clicks.get()
        self.engine.gain = self.speed.get()
        self.engine.invert_x, self.engine.invert_y = self.invert_x.get(), self.invert_y.get()
        if not self.engine.clicks:
            self.engine.tap.reset()

    def connect(self):
        if self.worker and self.worker.is_alive():
            self.note('A connection is already running. Stop it before changing the AAP service.')
            return
        self.session += 1
        session = self.session
        self.stop = threading.Event()
        self.live = None
        self.last_receive = 0
        self.rates.clear()
        self.engine = Engine()
        self.settings()
        self.status.set('Connecting — diagnostics do not move or click')
        def emit(value):
            try:
                self.events.put_nowait((session, time.monotonic(), value))
            except queue.Full:
                pass  # stale backlog is discarded and cannot control the pointer
        self.worker = threading.Thread(target=sensor_worker, args=(self.stop, emit, int(self.service.get())), daemon=True)
        self.worker.start()

    def disconnect(self):
        self.stop.set()
        self.pause('Connection stopped')
        self.capture = None
        self.live = None
        self.last_receive = 0

    def pause(self, reason):
        self.engine.pause()
        self.history.clear()
        self.arm_button.configure(text='Enable pointer control')
        self.status.set(reason)

    def fresh(self):
        return self.live is not None and time.monotonic() - self.last_receive < .15

    def calibrate(self, mode):
        if not self.fresh():
            self.note('No fresh motion data. Start diagnostics and fix the connection first.')
            return
        if mode != 'still' and self.engine.source is None:
            self.note('Do Hold still first.')
            return
        if mode == 'y' and self.engine.x_axis is None:
            self.note('Do Turn RIGHT before Tilt UP.')
            return
        self.pause('Calibration: get ready')
        self.capture = (mode, time.monotonic() + 1, time.monotonic() + 3)
        self.cal_samples = []
        self.guide.set('In 1 second: ' + {'still': 'hold perfectly still for 2 seconds.', 'x': 'turn slowly RIGHT 15–45 degrees; hold there until finished.', 'y': 'tilt the front UP 15–45 degrees; hold there until finished.'}[mode])

    def toggle(self):
        if self.engine.enabled:
            self.pause('Paused')
            return
        if self.capture or not self.fresh() or not self.engine.calibrated:
            self.note('Need fresh motion and all three calibration steps before enabling control.')
            return
        if not self.mouse.trusted():
            self.note('Grant Accessibility to Terminal/Python in macOS System Settings, then restart this app.')
            return
        self.engine.pause()
        self.engine.enabled = True
        self.cursor = self.mouse.position()
        self.history.clear()
        self.status.set('Pointer control ON')
        self.arm_button.configure(text='Pause pointer control')

    def sample(self, received, sample):
        if not sample.valid():
            self.pause('Invalid sensor data — paused')
            return
        self.live, self.last_receive = sample, received
        self.rates.append(received)
        if self.capture:
            _, start, end = self.capture
            if start <= received <= end:
                self.cal_samples.append(sample)
        was_enabled = self.engine.enabled
        dx, dy, tap = self.engine.process(sample)
        if was_enabled and not self.engine.enabled:
            self.pause('Stream changed or stalled — recalibrate if needed, then enable again')
        if not self.engine.enabled:
            return
        if self.mouse.emergency():
            self.pause('Emergency pause')
            return
        current = self.mouse.position()
        if abs(current[0] - self.cursor[0]) > 4 or abs(current[1] - self.cursor[1]) > 4:
            self.cursor = current
            self.history.clear()
            self.engine.tap.reset()
        if tap is not None:
            target = next((p for t, p in reversed(self.history) if t <= tap - .07), None)
            # Never click without a pre-impulse target from this uninterrupted session.
            if target is not None and self.clicks.get():
                self.mouse.move(*target)
                self.mouse.click()
                self.cursor = self.mouse.position()
        elif dx or dy:
            self.cursor = (max(4, min(self.mouse.width - 5, self.cursor[0] + dx)), max(4, min(self.mouse.height - 5, self.cursor[1] + dy)))
            self.mouse.move(*self.cursor)
        self.history.append((sample.t, self.cursor))

    def tick(self):
        try:
            now = time.monotonic()
            if self.engine.enabled and (not self.fresh() or self.mouse.emergency()):
                self.pause('Motion stopped or emergency pause — enable manually to resume')
            for _ in range(256):
                try:
                    session, received, value = self.events.get_nowait()
                except queue.Empty:
                    break
                if session != self.session or self.stop.is_set():
                    continue
                if isinstance(value, Sample):
                    if now - received <= .15:
                        self.sample(received, value)
                    else:
                        self.pause('Delayed sensor data — paused')
                elif 'error' in value:
                    self.pause('Sensor connection unavailable')
                    self.note(value['error'])
                elif 'reset' in value:
                    self.engine = Engine()
                    self.settings()
                    self.capture = None
                    self.pause(value['reset'])
                elif 'status' in value:
                    self.note(value['status'])
                elif 'ended' in value:
                    self.pause('Sensor connection ended')
                    self.capture = None
            while self.rates and now - self.rates[0] > 1:
                self.rates.popleft()
            if self.live:
                self.telemetry.set(f'{len(self.rates)} samples/sec | rotation {norm(self.live.gyro):.2f} rad/s | tap signal {norm(self.live.accel):.2f} g | {"calibrated" if self.engine.calibrated else "needs calibration"}')
            if self.fresh() and not self.engine.enabled and not self.capture:
                self.status.set('Live sensor data — pointer paused')
            if self.capture:
                mode, start, end = self.capture
                if now >= end:
                    self.capture = None
                    try:
                        if mode == 'still':
                            self.engine.calibrate_still(self.cal_samples)
                        else:
                            self.engine.set_axis(mode, self.cal_samples)
                        self.guide.set({'still': 'Stillness saved. Next: Turn RIGHT.', 'x': 'RIGHT saved. Next: Tilt UP.', 'y': 'Calibration complete. Enable pointer control; test movement before taps.'}[mode])
                        self.note('Calibration step saved: ' + mode)
                    except ValueError as exc:
                        self.guide.set(str(exc))
                        self.note(str(exc))
                elif now >= start:
                    self.status.set(f'Recording {mode.upper()} — {end - now:.1f}s remaining')
        except Exception as exc:
            self.pause('Stopped after an error')
            self.note(str(exc))
        self.root.after(15, self.tick)

    def close(self):
        self.stop.set()
        self.engine.pause()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose', action='store_true', help='List driver interface count only; no sensor commands or mouse movement')
    parser.add_argument('--smoke-seconds', type=float, help='Open idle UI briefly; do not connect or control')
    args = parser.parse_args()
    if args.diagnose:
        if sys.platform == 'win32':
            from windows_aap import interfaces
            print(json.dumps({'platform': sys.platform, 'connected_magic_aap_interfaces': len(interfaces()), 'mouse_control': False}))
        else:
            print(json.dumps({'platform': sys.platform, 'helper_built': (ROOT / 'native/CaseMotion.app/Contents/MacOS/CaseMotion').is_file(), 'mouse_control': False}))
        return
    root = tk.Tk()
    app = App(root)
    if args.smoke_seconds:
        root.after(int(args.smoke_seconds * 1000), app.close)
    root.mainloop()
    if app.worker:
        app.worker.join(timeout=3)


if __name__ == '__main__':
    main()
