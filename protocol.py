"""Experimental AAP SensorDataWX and RemoteHID parsing.

Wire-layout facts: MousePods by Matteo Gaudioso (starman-tech),
https://github.com/starman-tech/mousepods (see SOURCES.md for attribution).
Independent implementation; unknown/truncated formats are rejected.
"""
import math
import plistlib
import struct
from xml.parsers.expat import ExpatError
from engine import Sample

WX = bytes.fromhex('04000400170000001000')
RH = bytes.fromhex('04000400170000080000')
HANDSHAKE = bytes.fromhex('00000400010002000000000000000000')
NOTIFY = bytes.fromhex('040004000f00ffffffff')


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError('Truncated protobuf integer')
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('Oversized protobuf integer')


def fields(data):
    pos = 0
    while pos < len(data):
        key, pos = varint(data, pos)
        number, kind = key >> 3, key & 7
        if not number:
            raise ValueError('Invalid protobuf field')
        if kind == 0:
            value, pos = varint(data, pos)
        else:
            if kind == 2:
                size, pos = varint(data, pos)
            elif kind in (1, 5):
                size = 8 if kind == 1 else 4
            else:
                raise ValueError('Unsupported protobuf wire type')
            if pos + size > len(data):
                raise ValueError('Truncated protobuf field')
            value, pos = data[pos:pos + size], pos + size
        yield number, value


def wx_command(service=16, interval=20000, sequence=1):
    if not 0 <= service <= 127:
        raise ValueError('Service ID must be 0–127')
    body = bytes([8, sequence & 127, 0x42, 11, 8, service, 16, 2, 26, 5, 1]) + struct.pack('<I', interval)
    return WX + struct.pack('<H', len(body)) + body


def rh_command(device=0, kind=0, payload=b'', generation=0):
    size = len(payload) + 4
    if size > 1023:
        raise ValueError('RemoteHID command too large')
    header = (device & 127) | (size << 7) | (kind << 17)
    body = bytes([0, generation & 255, 0, 0]) + struct.pack('<I', header) + payload
    return RH + struct.pack('<H', len(body)) + body


def feature(device, interval, generation=0):
    return rh_command(device, 3, b'\x02\x01' + struct.pack('<I', interval), generation)


def block_sample(block, source):
    if len(block) != 58 or block[0] != 1:
        return None
    gyro = tuple(math.radians(x * .122) for x in struct.unpack_from('<hhh', block, 26))
    accel = tuple(x / 1000 for x in struct.unpack_from('<hhh', block, 38))
    gravity = tuple(x / 1000 for x in struct.unpack_from('<hhh', block, 44))
    sample = Sample(struct.unpack_from('<Q', block, 1)[0] / 1e9, gyro, accel, gravity, source)
    return sample if sample.valid() else None


class Decoder:
    def __init__(self, services=(14, 16)):
        self.services = set(services)
        self.remote_devices = set()

    def decode(self, packet):
        """Return samples and response commands for discovered RemoteHID sensors."""
        samples, commands = [], []
        if len(packet) < 12 or packet[:10] not in (WX, RH):
            return samples, commands
        size = struct.unpack_from('<H', packet, 10)[0]
        if size != len(packet) - 12:
            return samples, commands
        body = packet[12:]
        try:
            if packet[:10] == WX:
                for number, value in fields(body):
                    if number != 7 or not isinstance(value, bytes):
                        continue
                    nested = dict(fields(value))
                    block, service = nested.get(3), nested.get(1)
                    if service in self.services and isinstance(block, bytes):
                        sample = block_sample(block, f'aap-service-{service}')
                        if sample:
                            samples.append(sample)
            elif len(body) >= 4:
                pos = 4
                while pos + 4 <= len(body):
                    header = struct.unpack_from('<I', body, pos)[0]
                    length, kind, device = (header >> 7) & 1023, (header >> 17) & 7, header & 127
                    if length < 4 or pos + length > len(body):
                        return [], []
                    payload = body[pos + 4:pos + length]
                    pos += length
                    if kind == 0 and b'<?xml' in payload:
                        xml = payload[payload.index(b'<?xml'):]
                        end = xml.find(b'</plist>')
                        if end < 0:
                            continue
                        info = plistlib.loads(xml[:end + 8])
                        if info.get('AccessoryService') == 'devmotion6':
                            self.remote_devices.add(device)
                            commands.append(feature(device, 20000, body[1]))
                    elif kind == 2 and device in self.remote_devices and len(payload) == 59:
                        sample = block_sample(payload[1:], f'remotehid-{device}-side-{body[3]}')
                        if sample:
                            samples.append(sample)
                if pos != len(body):
                    return [], []
        except (ValueError, TypeError, struct.error, plistlib.InvalidFileException, ExpatError):
            return [], []
        return samples, commands
