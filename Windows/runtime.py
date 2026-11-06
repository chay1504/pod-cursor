"""Windows hardware/session worker. Requires an installed MagicAAP interface."""
from pathlib import Path
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from protocol import Reader,Session,HANDSHAKE,FLAGS,NOTIFICATIONS,sensor_setting
from taps import Taps
from transport import interfaces,Transport


class Orientation:
    def __init__(self):
        node=shutil.which('node')
        if not node:
            raise RuntimeError('Install Node.js 22+ to run the original orientation math.')
        self.process=subprocess.Popen([node,str(Path(__file__).with_name('orientation.mjs'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.output=queue.Queue()
        def read():
            for line in self.process.stdout:
                self.output.put(line)
            self.output.put(None)
        threading.Thread(target=read,daemon=True).start()

    def call(self,cmd,**kwargs):
        self.process.stdin.write(json.dumps({'cmd':cmd,**kwargs})+'\n')
        self.process.stdin.flush()
        try:
            line=self.output.get(timeout=2)
        except queue.Empty:
            raise TimeoutError('Orientation worker timed out')
        if line is None:
            raise RuntimeError('Orientation worker exited')
        result=json.loads(line)
        if result.get('error'):
            raise ValueError(result['error'])
        return result

    def close(self):
        self.process.terminate()
        try:self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:self.process.kill()


def run(stop,commands,emit,lease):
    transport=orientation=session=None
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'AirPointerWindows'
    seq_file=state/'sensor-sequence.txt'
    seq=8000
    attempted=[]
    def setting(service,interval):
        nonlocal seq
        seq+=1
        if not 8001<=seq<=16000:seq=8001
        state.mkdir(parents=True,exist_ok=True)
        temporary=seq_file.with_suffix('.tmp')
        temporary.write_text(str(seq),encoding='ascii')
        temporary.replace(seq_file)
        transport.send(sensor_setting(service,interval,seq))
    try:
        seq=int(seq_file.read_text().strip()) if seq_file.exists() else 8000
        paths=interfaces()
        if len(paths)!=1:
            raise RuntimeError('Need exactly one connected MagicAAP interface; found '+str(len(paths))+'. No Windows sensor driver is installed/connected here. Read Windows/README.md.')
        orientation=Orientation()
        transport=Transport(paths[0])
        reader=Reader()
        session=Session(transport.send)
        taps=Taps()
        emit({'status':'Session setup. Keep the lid OPEN until the app verifies live motion.'})
        for packet in (HANDSHAKE,FLAGS,NOTIFICATIONS):
            transport.send(packet)
            time.sleep(.15)
        for service in (11,12):
            attempted.append(service)
            setting(service,5000)
        began=time.monotonic();last_motion={};counts={11:0,12:0};baseline=False;last_status=0.;closed_at=None
        while not stop.is_set():
            now=time.monotonic()
            if now-lease[0]>5:
                raise TimeoutError('Application heartbeat expired; ending sensor session')
            try:
                while True:
                    cmd=commands.get_nowait()
                    if cmd=='closed':
                        if not baseline:
                            raise ValueError('Wait for verified open-lid motion before closing the lid.')
                        session.closed=True;closed_at=now
                        taps.reset();orientation.call('reset')
                        emit({'reset':True,'status':'Closed lid confirmed. Set the case down for sensor calibration.'})
                    elif cmd in ('center','right','up'):
                        if not session.case_verified or not all(now-last_motion.get(s,0)<.5 for s in (11,12)):
                            emit({'status':'Need verified case identity and fresh motion before aiming.'})
                            continue
                        try:emit({'model':orientation.call(cmd),'status':cmd.upper()+' saved'})
                        except ValueError as exc:emit({'status':str(exc)})
                    elif cmd=='reset':
                        taps.reset();emit({'model':orientation.call('reset'),'reset':True})
            except queue.Empty:pass
            packet=transport.transfer(timeout=80)
            now=time.monotonic()
            if packet==b'':
                raise RuntimeError('AirPods Bluetooth channel ended')
            if packet:
                rows,messages=reader.feed(packet,now)
                for message in messages:session.handle(message)
                if rows:
                    for row in rows:last_motion[row[1]]=now;counts[row[1]]+=1
                    model=orientation.call('rows',rows=rows)
                    emit({'model':model,'rows':rows,'taps':taps.feed(rows),'hold':taps.hold_until,'case_verified':session.case_verified,'received':now})
            session.tick()
            fresh=all(counts[s]>=25 and now-last_motion.get(s,0)<1 for s in (11,12))
            if fresh and session.root_verified and not baseline:
                baseline=True
                emit({'baseline':True,'status':'Live open-lid motion verified. CLOSE the lid, then click Confirm lid closed.'})
            if now-last_status>1:
                emit({'stats':counts.copy(),'case_verified':session.case_verified,'closed':session.closed})
                last_status=now
            if counts[11] and counts[12] and any(now-last_motion.get(s,now)>3 for s in (11,12)):
                raise TimeoutError('Raw motion stopped for more than 3 seconds')
            if not fresh and not baseline and now-began>15:
                raise TimeoutError('No verified open-lid motion. Reconnect AirPods in Windows settings, then retry immediately with lid open.')
            if not session.root_verified and now-began>160:
                raise TimeoutError('AirPods Pro identity did not verify')
            if closed_at and now-closed_at>=1800:
                raise TimeoutError('30-minute case session ended. Open the lid and connect again.')
    except Exception as exc:
        if session:session.error=str(exc)
        emit({'error':str(exc)})
    finally:
        errors=[]
        if transport:
            for service in attempted:
                try:setting(service,0)
                except Exception as exc:errors.append('Sensor STOP failed: '+str(exc))
            if session:
                try:
                    session.cleanup()
                    deadline=time.monotonic()+1.5
                    while session.cleanup_sent and not session.cleanup_ack and time.monotonic()<deadline:
                        packet=transport.transfer(timeout=100)
                        if packet:
                            _,messages=reader.feed(packet,time.monotonic())
                            for message in messages:session.handle(message)
                    if session.cleanup_sent and not session.cleanup_ack:errors.append('Case diagnostic release was not acknowledged')
                except Exception as exc:errors.append('Case cleanup failed: '+str(exc))
            transport.close()
        if orientation:orientation.close()
        for error in errors:emit({'error':error})
        emit({'ended':True})
