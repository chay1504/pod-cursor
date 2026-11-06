from pathlib import Path
import sys
import time
import tkinter as tk
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import App


class FakeMouse:
    width,height=1920,1080
    def __init__(self):self.events=[];self.point=(500,500);self.stop=False
    def position(self):return self.point
    def emergency(self):return self.stop
    def move(self,point):self.point=point;self.events.append(('move',point))
    def click(self):self.events.append(('click',))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.mouse=FakeMouse();self.app=App(self.root,self.mouse)
    def tearDown(self):self.app.close()
    def ready(self):
        self.app.verified=True;self.app.last=time.monotonic();self.app.model={'calibrated':True,'point':[.5,.5]}
    def event(self,age=0):
        self.app.events.put((self.app.generation,time.monotonic()-age,{'model':{'ready':True,'calibrated':True,'point':[.7,.4]},'rows':[[1,12,1000000,0,0,0,0]],'taps':[],'case_verified':True}))
    def test_starts_disconnected_and_never_posts_events(self):
        self.event();self.app.tick();self.assertFalse(self.app.active);self.assertEqual(self.mouse.events,[])
    def test_calibration_is_required_to_enable(self):
        self.app.toggle();self.assertFalse(self.app.active)
    def test_stale_queued_data_pauses(self):
        self.ready();self.app.toggle();self.event(age=1);self.app.tick()
        self.assertFalse(self.app.active);self.assertEqual(self.mouse.events,[])
    def test_emergency_precedes_output(self):
        self.ready();self.app.toggle();self.mouse.stop=True;self.event();self.app.tick()
        self.assertFalse(self.app.active);self.assertEqual(self.mouse.events,[])
    def test_taps_start_disabled(self):self.assertFalse(self.app.clicks.get())
    def test_closed_session_is_required(self):
        self.ready();self.app.verified=False;self.app.toggle();self.assertFalse(self.app.active)


if __name__=='__main__':unittest.main()
