"""Windows AAP backend. Uses an ALREADY INSTALLED MagicAAP driver.

Never installs a driver or changes boot/signing/security settings.
Implements documented Win32 API calls independently; protocol references in SOURCES.md.
"""
import ctypes as C
from ctypes import wintypes as W
import struct
import sys
import time


class GUID(C.Structure):
    _fields_ = [('a', W.DWORD), ('b', W.WORD), ('c', W.WORD), ('d', C.c_ubyte * 8)]


class Interface(C.Structure):
    _fields_ = [('size', W.DWORD), ('guid', GUID), ('flags', W.DWORD), ('reserved', C.c_size_t)]


class Overlapped(C.Structure):
    _fields_ = [('internal', C.c_size_t), ('internal_high', C.c_size_t),
                ('offset', W.DWORD), ('offset_high', W.DWORD), ('event', W.HANDLE)]


def api():
    if sys.platform != 'win32':
        raise RuntimeError('MagicAAP backend requires Windows.')
    setup = C.WinDLL('setupapi', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    signatures = [
        (setup, 'SetupDiGetClassDevsW', [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD], W.HANDLE),
        (setup, 'SetupDiEnumDeviceInterfaces', [W.HANDLE, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(Interface)], W.BOOL),
        (setup, 'SetupDiGetDeviceInterfaceDetailW', [W.HANDLE, C.POINTER(Interface), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
        (setup, 'SetupDiDestroyDeviceInfoList', [W.HANDLE], W.BOOL),
        (kernel, 'CreateFileW', [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE),
        (kernel, 'ReadFile', [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(Overlapped)], W.BOOL),
        (kernel, 'WriteFile', [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(Overlapped)], W.BOOL),
        (kernel, 'CreateEventW', [C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR], W.HANDLE),
        (kernel, 'WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD),
        (kernel, 'GetOverlappedResult', [W.HANDLE, C.POINTER(Overlapped), C.POINTER(W.DWORD), W.BOOL], W.BOOL),
        (kernel, 'CancelIoEx', [W.HANDLE, C.POINTER(Overlapped)], W.BOOL),
        (kernel, 'CloseHandle', [W.HANDLE], W.BOOL)]
    for lib, name, args, result in signatures:
        function = getattr(lib, name)
        function.argtypes, function.restype = args, result
    return setup, kernel


def interfaces():
    setup, _ = api()
    guid = GUID(0x9eec98bb, 0x3c54, 0x45d4, (C.c_ubyte * 8)(0xa8, 0x43, 0x79, 0, 0xc4, 0x63, 0x5e, 8))
    handle = setup.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    found = []
    try:
        index = 0
        while True:
            item = Interface()
            item.size = C.sizeof(item)
            if not setup.SetupDiEnumDeviceInterfaces(handle, None, C.byref(guid), index, C.byref(item)):
                error = C.get_last_error()
                if error == 259:
                    break
                raise C.WinError(error)
            needed = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(handle, C.byref(item), None, 0, C.byref(needed), None)
            if needed.value < 8 or needed.value > 65536:
                raise RuntimeError('Unexpected driver interface size.')
            detail = C.create_string_buffer(needed.value)
            struct.pack_into('<I', detail, 0, 8 if C.sizeof(C.c_void_p) == 8 else 6)
            if not setup.SetupDiGetDeviceInterfaceDetailW(handle, C.byref(item), detail, needed, None, None):
                raise C.WinError(C.get_last_error())
            found.append(C.wstring_at(C.addressof(detail) + 4))
            index += 1
    finally:
        setup.SetupDiDestroyDeviceInfoList(handle)
    return found


class Transport:
    def __init__(self, path):
        _, self.kernel = api()
        self.handle = self.kernel.CreateFileW(path, 0xc0000000, 3, None, 3, 0x40000000, None)
        if self.handle == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())

    def transfer(self, data=None, timeout=300):
        kernel = self.kernel
        event = kernel.CreateEventW(None, True, False, None)
        if not event:
            raise C.WinError(C.get_last_error())
        overlap = Overlapped()
        overlap.event = event
        buffer = C.create_string_buffer(data, len(data)) if data is not None else C.create_string_buffer(8192)
        count = W.DWORD()
        try:
            operation = kernel.WriteFile if data is not None else kernel.ReadFile
            ok = operation(self.handle, buffer, len(buffer), C.byref(count), C.byref(overlap))
            if not ok:
                error = C.get_last_error()
                if error != 997:
                    raise C.WinError(error)
                result = kernel.WaitForSingleObject(event, timeout)
                if result != 0:
                    kernel.CancelIoEx(self.handle, C.byref(overlap))
                    # Keep OVERLAPPED/buffer alive until the driver acknowledges cancellation.
                    kernel.GetOverlappedResult(self.handle, C.byref(overlap), C.byref(count), True)
                    if result == 258:
                        return None
                    raise C.WinError(C.get_last_error())
                if not kernel.GetOverlappedResult(self.handle, C.byref(overlap), C.byref(count), False):
                    raise C.WinError(C.get_last_error())
            if data is not None and count.value != len(data):
                raise RuntimeError('Partial AAP command write.')
            return buffer.raw[:count.value]
        finally:
            kernel.CloseHandle(event)

    def send(self, data):
        if self.transfer(data, 1000) is None:
            raise RuntimeError('AAP command timed out.')

    def close(self):
        self.kernel.CloseHandle(self.handle)


def stream(stop, emit, service=16):
    from protocol import HANDSHAKE, NOTIFY, Decoder, wx_command, rh_command, feature
    paths = interfaces()
    if not paths:
        raise RuntimeError('No connected MagicAAP sensor interface. Ordinary Bluetooth audio is not sensor access. See WINDOWS-STATUS.md.')
    if len(paths) != 1:
        raise RuntimeError('More than one AAP interface found. Disconnect other AirPods before retrying.')
    transport, decoder = Transport(paths[0]), Decoder((service,))
    try:
        emit({'status': 'Connecting to the installed AAP driver. Case mode is experimental on Windows.'})
        transport.send(HANDSHAKE)
        if not transport.transfer(timeout=2000):
            raise RuntimeError('No AAP handshake response. Open the case and close competing AAP apps.')
        transport.send(NOTIFY)
        transport.send(wx_command(service))
        transport.send(rh_command())
        last_motion = time.monotonic()
        last_ear = None
        while not stop.is_set():
            packet = transport.transfer()
            if packet:
                if packet[:6] == bytes.fromhex('040004000600') and len(packet) >= 8:
                    ear = packet[6:8]
                    if last_ear is not None and ear != last_ear:
                        emit({'reset': 'Earbud state changed. Recalibrate before controlling the pointer.'})
                    last_ear = ear
                samples, commands = decoder.decode(packet)
                for command in commands:
                    transport.send(command)
                for sample in samples:
                    emit(sample)
                    last_motion = time.monotonic()
            if time.monotonic() - last_motion > 15:
                raise RuntimeError('No recognised live motion for 15 seconds. This device/firmware/case state is not yet supported by this Windows adapter.')
    finally:
        try:
            transport.send(wx_command(service, 0, 2))
            for device in decoder.remote_devices:
                transport.send(feature(device, 0))
        finally:
            transport.close()
