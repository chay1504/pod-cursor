"""Windows pointer output; no administrator access or driver changes."""
import ctypes as C
from ctypes import wintypes as W


class Mouse:
    def __init__(self):
        self.api=C.WinDLL('user32',use_last_error=True)
        self.api.SetProcessDPIAware()
        self.width,self.height=self.api.GetSystemMetrics(0),self.api.GetSystemMetrics(1)
        self.api.GetCursorPos.argtypes=[C.POINTER(W.POINT)]
        self.api.GetCursorPos.restype=W.BOOL
        self.api.SetCursorPos.argtypes=[C.c_int,C.c_int]
        self.api.SetCursorPos.restype=W.BOOL
        self.api.GetAsyncKeyState.argtypes=[C.c_int]
        self.api.GetAsyncKeyState.restype=C.c_short
        self.api.mouse_event.argtypes=[W.DWORD,W.DWORD,W.DWORD,W.DWORD,C.c_size_t]

    def position(self):
        p=W.POINT()
        if not self.api.GetCursorPos(C.byref(p)):raise C.WinError(C.get_last_error())
        return p.x,p.y

    def emergency(self):
        x,y=self.position()
        corner=(x<=2 or x>=self.width-3) and (y<=2 or y>=self.height-3)
        return corner or all(self.api.GetAsyncKeyState(k)&0x8000 for k in (0x11,0x12,0x51))

    def move(self,point):
        x,y=point
        if not self.api.SetCursorPos(round(max(4,min(self.width-5,x))),round(max(4,min(self.height-5,y)))):
            raise C.WinError(C.get_last_error())

    def click(self):
        self.api.mouse_event(2,0,0,0,0)
        self.api.mouse_event(4,0,0,0,0)
