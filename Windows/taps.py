"""Translation of Andy Gao's ClosedCaseTapDetector (MIT, root LICENSE).
Raw accelerometer service 11 is in g; gyro service 12 is in degrees/sec.
"""
import math


def length(v):
    return math.sqrt(sum(x*x for x in v))


class Taps:
    def __init__(self):
        v=(-.84,.29,-.46)
        self.direction=tuple(x/length(v) for x in v)
        self.last_tap=self.run_from=-math.inf
        self.peak=0.
        self.reset()

    def reset(self):
        self.recent=[]
        self.rotation=None
        self.hold_until=None
        self.run_from=-math.inf

    def still(self,end):
        earlier=[s for s in self.recent if s[0]<end]
        window=[s for s in earlier if end-s[0]<=.15]
        while len(window)<3 or end-(window[0][0] if window else end)<.13:
            more=[s for s in earlier if s[0]<(window[0][0] if window else end)]
            if not more or end-more[-1][0]>.4:
                break
            window.insert(0,more[-1])
        if len(window)<3 or end-window[0][0]<.13:
            return None
        base=tuple(sum(s[1][i] for s in window)/len(window) for i in range(3))
        if all(length(s[2])<=40 and length(tuple(x-y for x,y in zip(s[1],base)))<=.08 for s in window):
            return base

    def feed(self,rows):
        events=[]
        for row in sorted(rows,key=lambda r:r[2]):
            _,service,stamp,host,*raw=row
            t=stamp*1e-6
            v=tuple(x*1e-5 for x in raw)
            if not all(math.isfinite(x) for x in (t,*v)):
                continue
            if service==12:
                self.rotation=(t,v)
                continue
            if service!=11 or self.recent and t<=self.recent[-1][0]:
                continue
            if not self.rotation or abs(self.rotation[0]-t)>.25:
                self.recent=[];self.hold_until=None
                continue
            if self.recent and t-self.recent[-1][0]>.25:
                self.recent=[];self.hold_until=None
            s=(t,v,self.rotation[1])
            if self.hold_until is not None and t>=self.hold_until:
                self.hold_until=None
            prior=[r for r in self.recent if t-r[0]>=.015]
            before=prior[-1] if prior else (self.recent[0] if self.recent else None)
            if before and t-before[0]<=.05:
                spike=tuple(x-y for x,y in zip(v,before[1]))
                size=length(spike);along=sum(x*y for x,y in zip(spike,self.direction))
                if t-self.last_tap<=.03:
                    self.peak=max(self.peak,along)
                if t-self.last_tap>=.12 and size>=.12 and along>=size*.9 and along>=.2:
                    lead=[length(r[2]) for r in self.recent if t-.1<=r[0]<=t-.02]
                    just=[length(r[2]) for r in self.recent if t-.12<=r[0]<=t-.02]
                    lead=max(lead,default=0);just=max(just) if just else None
                    firm=along>=.3 and along>=size*.95
                    base=self.still(t-.1)
                    first=base is not None and lead<=(60 if firm else 30)
                    exact=firm and just is not None and just<=45
                    repeated=(t-self.run_from<=1 and (self.run_from==self.last_tap or t-self.run_from>=.06)
                              and along>=.22 and just is not None and just<=(90 if firm else 45))
                    echo_ok=t-self.last_tap>=.25 or repeated and along>=self.peak*.7 and just is not None and just<=35
                    if echo_ok and (first or repeated or exact):
                        drift=next((r[0] for r in self.recent if r[0]>=t-.1 and base is not None and length(tuple(x-y for x,y in zip(r[1],base)))>.08),None)
                        events.append({'since':min(drift if drift is not None else before[0],before[0]),'jolt':along})
                        self.last_tap,self.peak,self.run_from,self.hold_until=t,along,t,t+.2
                    elif echo_ok and along>=.22 and just is not None and just<=150:
                        self.run_from=t
            self.recent.append(s)
            self.recent=[r for r in self.recent if t-r[0]<=.75]
        return events
