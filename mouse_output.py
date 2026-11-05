"""Minimal native mouse output. No button is ever left held down."""
import ctypes as C
import sys


class Mouse:
    def __init__(self):
        if sys.platform == 'win32':
            from ctypes import wintypes as W
            self.lib = C.WinDLL('user32', use_last_error=True)
            self.lib.SetProcessDPIAware()
            self.width, self.height = self.lib.GetSystemMetrics(0), self.lib.GetSystemMetrics(1)
            self.point_type = W.POINT
            self.lib.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
            self.lib.GetCursorPos.restype = W.BOOL
            self.lib.SetCursorPos.argtypes = [C.c_int, C.c_int]
            self.lib.SetCursorPos.restype = W.BOOL
            self.lib.GetAsyncKeyState.argtypes = [C.c_int]
            self.lib.GetAsyncKeyState.restype = C.c_short
            self.lib.mouse_event.argtypes = [W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
        elif sys.platform == 'darwin':
            class Point(C.Structure):
                _fields_ = [('x', C.c_double), ('y', C.c_double)]
            class Size(C.Structure):
                _fields_ = [('width', C.c_double), ('height', C.c_double)]
            class Rect(C.Structure):
                _fields_ = [('origin', Point), ('size', Size)]
            self.point_type = Point
            self.lib = C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
            self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            self.ax = C.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
            self.ax.AXIsProcessTrusted.restype = C.c_bool
            self.cf.CFRelease.argtypes = [C.c_void_p]
            self.lib.CGMainDisplayID.restype = C.c_uint32
            self.lib.CGDisplayBounds.argtypes = [C.c_uint32]
            self.lib.CGDisplayBounds.restype = Rect
            bounds = self.lib.CGDisplayBounds(self.lib.CGMainDisplayID())
            self.width, self.height = int(bounds.size.width), int(bounds.size.height)
            self.lib.CGEventCreate.argtypes, self.lib.CGEventCreate.restype = [C.c_void_p], C.c_void_p
            self.lib.CGEventGetLocation.argtypes, self.lib.CGEventGetLocation.restype = [C.c_void_p], Point
            self.lib.CGEventCreateMouseEvent.argtypes = [C.c_void_p, C.c_uint32, Point, C.c_uint32]
            self.lib.CGEventCreateMouseEvent.restype = C.c_void_p
            self.lib.CGEventPost.argtypes = [C.c_uint32, C.c_void_p]
            self.lib.CGEventSourceKeyState.argtypes, self.lib.CGEventSourceKeyState.restype = [C.c_uint32, C.c_uint16], C.c_bool
        else:
            raise RuntimeError('Only Windows and macOS are implemented.')

    def trusted(self):
        return sys.platform == 'win32' or self.ax.AXIsProcessTrusted()

    def position(self):
        if sys.platform == 'win32':
            p = self.point_type()
            if not self.lib.GetCursorPos(C.byref(p)):
                raise C.WinError(C.get_last_error())
        else:
            event = self.lib.CGEventCreate(None)
            if not event:
                raise RuntimeError('Cannot read the pointer position.')
            try:
                p = self.lib.CGEventGetLocation(event)
            finally:
                self.cf.CFRelease(event)
        return float(p.x), float(p.y)

    def emergency(self):
        x, y = self.position()
        corner = (x <= 2 or x >= self.width - 3) and (y <= 2 or y >= self.height - 3)
        if sys.platform == 'win32':
            chord = all(self.lib.GetAsyncKeyState(k) & 0x8000 for k in (0x11, 0x12, 0x51))
        else:
            chord = all(self.lib.CGEventSourceKeyState(0, k) for k in (59, 58, 12))
        return corner or chord

    def move(self, x, y):
        x, y = round(max(4, min(self.width - 5, x))), round(max(4, min(self.height - 5, y)))
        if sys.platform == 'win32':
            if not self.lib.SetCursorPos(x, y):
                raise C.WinError(C.get_last_error())
        else:
            self._event(5, x, y)

    def _event(self, kind, x, y):
        event = self.lib.CGEventCreateMouseEvent(None, kind, self.point_type(x, y), 0)
        if not event:
            raise RuntimeError('Cannot create mouse event. Check Accessibility permission.')
        try:
            self.lib.CGEventPost(0, event)
        finally:
            self.cf.CFRelease(event)

    def click(self):
        if sys.platform == 'win32':
            self.lib.mouse_event(2, 0, 0, 0, 0)
            self.lib.mouse_event(4, 0, 0, 0, 0)
        else:
            x, y = self.position()
            self._event(1, x, y)
            self._event(2, x, y)
