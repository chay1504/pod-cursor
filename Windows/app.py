"""Experimental Windows closed-case AirPointer port; no camera or marker input."""
from collections import deque
import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from mouse import Mouse
from runtime import run
from transport import interfaces


class App:
    def __init__(self,root,mouse=None):
        self.root,self.mouse=root,mouse or Mouse()
        self.stop=threading.Event();self.commands=queue.Queue();self.events=queue.Queue(maxsize=256)
        self.worker=None;self.lease=[time.monotonic()];self.active=False;self.model={};self.verified=False
        self.last=0.;self.generation=0;self.history=deque(maxlen=200);self.freeze_until=0.
        self.last_stats=None;self.last_stats_at=time.monotonic();self.ended=False
        self.status=tk.StringVar(value='Disconnected — scan the Windows driver first')
        self.guide=tk.StringVar(value='Original Mac code is preserved. This Windows port is not hardware-validated.')
        self.rate=tk.StringVar(value='No raw accelerometer/gyro samples')
        self.accept=tk.BooleanVar();self.clicks=tk.BooleanVar()
        root.title('AirPointer — Windows experimental port');root.geometry('800x720')
        box=ttk.Frame(root,padding=22);box.pack(fill='both',expand=True)
        ttk.Label(box,text='AirPointer · Windows',font=('Segoe UI',24,'bold')).pack(anchor='w')
        ttk.Label(box,text='Closed-case sensor connection · experimental',font=('Segoe UI',11)).pack(anchor='w',pady=(0,14))
        ttk.Label(box,text='Requires compatible AirPods Pro and an installed MagicAAP driver.\nUse speakers and the laptop microphone; close apps using the AirPods microphone.\nReconnect AirPods in Windows Bluetooth settings just before connecting here.',wraplength=740).pack(anchor='w')
        ttk.Checkbutton(box,text='I understand sessions can consume stored case diagnostics and change AirPods connection settings.',variable=self.accept).pack(anchor='w',pady=10)
        row=ttk.Frame(box);row.pack(fill='x')
        ttk.Button(row,text='Scan driver (read only)',command=self.scan).pack(side='left')
        ttk.Button(row,text='Connect with lid OPEN',command=self.connect).pack(side='left',padx=8)
        ttk.Button(row,text='Disconnect',command=self.disconnect).pack(side='left')
        ttk.Label(box,textvariable=self.status,font=('Segoe UI',11,'bold'),wraplength=740).pack(anchor='w',pady=12)
        ttk.Label(box,textvariable=self.rate).pack(anchor='w')
        ttk.Button(box,text='Confirm lid CLOSED',command=lambda:self.command('closed')).pack(anchor='w',pady=8)
        ttk.Label(box,textvariable=self.guide,wraplength=740).pack(anchor='w',pady=8)
        row=ttk.Frame(box);row.pack(fill='x')
        for label,cmd in [('Aim at CENTER','center'),('Aim at RIGHT edge','right'),('Aim at TOP edge','up')]:
            ttk.Button(row,text=label,command=lambda c=cmd:self.command(c)).pack(side='left',padx=(0,8))
        self.control=ttk.Button(box,text='Enable pointer',command=self.toggle)
        self.control.pack(anchor='w',pady=12)
        ttk.Checkbutton(box,text='Enable front-tap left-clicks (default off)',variable=self.clicks).pack(anchor='w')
        ttk.Button(box,text='Reset calibration',command=lambda:self.command('reset')).pack(anchor='w',pady=6)
        ttk.Label(box,text='Pause: Ctrl+Alt+Q, the pause button, or your physical mouse in a main-screen corner.\nThe app does not change Windows security, install drivers, or alter audio routing.',wraplength=740).pack(anchor='w',pady=10)
        self.log=tk.Text(box,height=8,wrap='word',state='disabled');self.log.pack(fill='both',expand=True)
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(15,self.tick)

    def note(self,message):
        self.log.configure(state='normal');self.log.insert('end',message+'\n');self.log.see('end')
        if int(self.log.index('end-1c').split('.')[0])>100:self.log.delete('1.0','20.0')
        self.log.configure(state='disabled')

    def scan(self):
        try:
            count=len(interfaces());self.status.set(f'{count} connected MagicAAP interface(s)')
            if not count:self.note('No usable sensor channel. Bluetooth audio pairing is insufficient. See Windows/README.md; no driver changes were made.')
        except Exception as exc:self.note(str(exc))

    def pause(self,message='Paused'):
        self.active=False;self.history.clear();self.control.configure(text='Enable pointer');self.status.set(message)

    def connect(self):
        if self.worker and self.worker.is_alive():self.note('A session is already running.');return
        if not self.accept.get():self.note('Read the diagnostic-data/settings notice before starting a session.');return
        self.pause('Connecting; keep lid open');self.model={};self.last=0.;self.verified=False
        self.stop=threading.Event();self.commands=queue.Queue();self.ended=False
        self.generation+=1;generation=self.generation
        self.lease[0]=time.monotonic();self.last_stats=None;self.last_stats_at=time.monotonic()
        def emit(value):
            try:self.events.put_nowait((generation,time.monotonic(),value))
            except queue.Full:self.stop.set()
        self.worker=threading.Thread(target=run,args=(self.stop,self.commands,emit,self.lease),daemon=True);self.worker.start()

    def command(self,name):
        if not self.worker or not self.worker.is_alive() or self.stop.is_set():self.note('Connect to a live sensor session first.');return
        self.pause('Calibration/connection step: '+name);self.commands.put(name)

    def disconnect(self):
        self.stop.set();self.pause('Stopping sensors and releasing diagnostic session…');self.last=0.

    def toggle(self):
        if self.active:self.pause();return
        if self.stop.is_set() or self.ended or not self.verified or not self.model.get('calibrated') or time.monotonic()-self.last>.15:
            self.note('Need fresh motion, verified case identity, and all three aiming points first.');return
        self.active=True;self.history.clear();self.status.set('Pointer ON');self.control.configure(text='Pause pointer')

    def tick(self):
        self.lease[0]=now=time.monotonic()
        try:
            if self.active and (now-self.last>.15 or self.mouse.emergency()):self.pause('Paused: motion gap or emergency stop')
            for _ in range(256):
                try:generation,received,value=self.events.get_nowait()
                except queue.Empty:break
                if generation!=self.generation:continue
                if 'error'in value:self.pause('Session error');self.note(value['error'])
                if 'ended'in value:self.ended=True;self.pause('Disconnected');continue
                if 'status'in value:self.guide.set(value['status']);self.note(value['status'])
                if value.get('reset'):self.model={};self.pause('Set down the case, then calibrate aiming')
                if 'stats'in value:
                    counts=value['stats'];previous=self.last_stats or {11:0,12:0};elapsed=max(.01,now-self.last_stats_at)
                    self.rate.set('Raw samples/sec — accel '+str(round((counts[11]-previous[11])/elapsed))+' | gyro '+str(round((counts[12]-previous[12])/elapsed)))
                    self.last_stats,self.last_stats_at=counts,now
                if 'case_verified'in value:self.verified=value['case_verified']
                if 'model'not in value:continue
                self.model=value['model']
                if not value.get('rows'):continue
                if now-received>.15 or self.stop.is_set() or self.ended:self.pause('Paused: stale queued motion');continue
                self.last=received
                if self.model.get('ready') and not self.model.get('calibrated'):
                    self.guide.set('Sensor offset ready. Aim at the CENTER and save; then RIGHT edge; then TOP edge.')
                if not self.active:continue
                if self.mouse.emergency():self.pause('Emergency pause');continue
                if not self.model.get('calibrated') or not self.verified:self.pause('Recalibration required');continue
                stamp=max(row[2] for row in value['rows'])*1e-6
                hold=value.get('hold')
                if value.get('taps') and self.clicks.get():
                    for tap in value['taps']:
                        target=next((p for t,p in reversed(self.history) if t<=tap['since']),None)
                        if target is not None:self.mouse.move(target);self.mouse.click()
                    self.freeze_until=hold or stamp+.2
                elif self.model.get('point') and stamp>=self.freeze_until and (not self.clicks.get() or hold is None):
                    x,y=self.model['point'];self.mouse.move((x*self.mouse.width,y*self.mouse.height))
                self.history.append((stamp,self.mouse.position()))
        except Exception as exc:self.pause('Stopped after error');self.note(str(exc));self.stop.set()
        self.root.after(15,self.tick)

    def close(self):
        self.stop.set();self.active=False;self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose',action='store_true')
    parser.add_argument('--smoke-seconds',type=float)
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Use the original build.sh on macOS.')
    if args.diagnose:
        print(json.dumps({'magic_aap_interfaces':len(interfaces()),'device_commands_sent':False,'mouse_control':False}));return
    root=tk.Tk();app=App(root)
    if args.smoke_seconds:root.after(int(args.smoke_seconds*1000),app.close)
    root.mainloop()
    if app.worker:app.worker.join(timeout=4)


if __name__=='__main__':main()
