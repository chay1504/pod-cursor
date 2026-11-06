"""Experimental Windows translation of AirPointer's closed-case protocol.

Based on Andy Gao's MIT-licensed CaseSustainedRenewal.m at a73cc798.
No firmware/data reads, arbitrary writes or driver installation are exposed.
"""
from collections import deque
import re
import struct
import time

HEADER = bytes.fromhex('04000400')
HANDSHAKE = bytes.fromhex('00000400010002000000000000000000')
FLAGS = bytes.fromhex('040004004d00ff00000000000000')
NOTIFICATIONS = bytes.fromhex('040004000f00ffffffff')


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def fields(data):
    def integer(pos):
        value = 0
        for shift in range(0, 64, 7):
            if pos >= len(data):
                raise ValueError('Truncated protobuf')
            byte = data[pos]
            pos += 1
            if shift == 63 and byte > 1:
                raise ValueError('Oversized integer')
            value |= (byte & 127) << shift
            if byte < 128:
                return value, pos
        raise ValueError('Oversized integer')
    pos = 0
    while pos < len(data):
        key, pos = integer(pos)
        if not key >> 3:
            raise ValueError('Invalid protobuf field')
        kind = key & 7
        if kind == 0:
            value, pos = integer(pos)
        else:
            if kind == 2:
                size, pos = integer(pos)
            elif kind in (1, 5):
                size = 8 if kind == 1 else 4
            else:
                raise ValueError('Unknown protobuf type')
            if pos + size > len(data):
                raise ValueError('Truncated protobuf field')
            value, pos = data[pos:pos + size], pos + size
        yield key >> 3, value


def sensor_setting(service, interval, sequence):
    if service not in (11, 12) or interval not in (0, 5000):
        raise ValueError('Only known accelerometer/gyro start and stop are allowed')
    setting = bytes([8, service, 16, 2, 26, 5, 1]) + struct.pack('<I', interval)
    message = b'\x08' + varint(sequence) + b'\x42' + varint(len(setting)) + setting
    return HEADER + bytes.fromhex('170000001000') + struct.pack('<H', len(message)) + message


def uarp(kind, identifier, body=b''):
    return struct.pack('>HHH', kind, len(body), identifier) + body


def envelope(message):
    return HEADER + b'\x4f\0' + struct.pack('<H', len(message)) + message


def unpack(message):
    if len(message) < 6:
        raise ValueError('Short UARP frame')
    kind, size, identifier = struct.unpack_from('>HHH', message)
    if size != len(message) - 6:
        raise ValueError('Malformed UARP frame')
    return kind, identifier, message[6:]


def model(body):
    if len(body) < 10:
        raise ValueError('Short identity response')
    status, prop, size = struct.unpack_from('>HII', body)
    if status or prop != 2 or size != len(body) - 10 or size > 128:
        raise ValueError('Invalid identity response')
    return body[10:].decode('utf8').strip(' \t\r\n\0').lower()


class Reader:
    def __init__(self):
        self.buffer = bytearray()
        self.latest = {}
        self.count = 0

    def feed(self, chunk, now):
        self.buffer.extend(chunk)
        if len(self.buffer) > 262144:
            raise ValueError('Input buffer limit exceeded')
        rows, messages = [], []
        while len(self.buffer) >= 6:
            if self.buffer[:4] != HEADER:
                del self.buffer[0]
                continue
            opcode = struct.unpack_from('<H', self.buffer, 4)[0]
            if opcode == 0x4f:
                if len(self.buffer) < 8:
                    break
                size = struct.unpack_from('<H', self.buffer, 6)[0]
                if size < 6 or size > 32768:
                    raise ValueError('Invalid UARP size')
                if len(self.buffer) < 8 + size:
                    break
                message = bytes(self.buffer[8:8 + size])
                unpack(message)
                messages.append(message)
                del self.buffer[:8 + size]
            elif opcode == 0x17:
                if len(self.buffer) < 12:
                    break
                descriptor, size = struct.unpack_from('<IH', self.buffer, 6)
                if len(self.buffer) < 12 + size:
                    break
                payload = bytes(self.buffer[12:12 + size])
                del self.buffer[:12 + size]
                if descriptor != 0x100000:
                    continue
                for number, value in fields(payload):
                    if number != 7 or not isinstance(value, bytes):
                        continue
                    inner = dict(fields(value))
                    service, report = inner.get(1), inner.get(3)
                    if service not in (11, 12) or not isinstance(report, bytes) or len(report) != 28 or report[0] != 1:
                        continue
                    stamp = struct.unpack_from('<Q', report, 20)[0]
                    if stamp <= self.latest.get(service, 0):
                        continue
                    self.latest[service] = stamp
                    self.count += 1
                    rows.append([self.count, service, stamp, now, *struct.unpack_from('<iii', report, 1)])
            elif opcode == 6:
                if len(self.buffer) < 8:
                    break
                del self.buffer[:8]  # UI explicitly confirms the closed lid; do not guess from these codes.
            else:
                del self.buffer[:6]
        return rows, messages


class Session:
    """Strict identity-gated UARP/MTIC lifecycle, with cleanup budget reserved.

    Windows lacks the original Mac reconnect and audio routing services. These
    remain explicit manual setup requirements; no successful hardware claim.
    """
    def __init__(self, send, clock=time.monotonic):
        self.send, self.clock = send, clock
        self.root_id = self.child_id = 1
        self.root_version = self.root_verified = self.case_active = False
        self.root_model_sent = self.discovery = False
        self.case_version = self.case_verified = self.case_model_sent = False
        self.closed = self.accepted = self.cleaning = self.cleanup_sent = self.cleanup_ack = False
        self.case_identity = None
        self.announced = set()
        self.responses = deque(maxlen=128)
        self.root_pending = False
        self.root_unanswered = self.root_startup = 0
        self.root_at = self.next_root = self.root_model_at = 0.
        self.version_frames = self.version_replies = self.model_after_frames = 0
        self.unknown_bytes = self.unconfirmed = self.init_bytes = 0
        self.next_case_version = 0.
        self.pending = None
        self.pending_at = 0.
        self.solicited = self.receipt = False
        self.last_solicit = 0.
        self.offer = None
        self.asset = None
        self.next_identity = 0.
        self.budget = deque()
        self.error = None

    def root(self, kind, body=b''):
        allowed = ((kind == 1 and body == b'\0\x07') or
                   (kind == 3 and self.root_version and not self.root_model_sent and body == b'\0\0\0\x02') or
                   (kind == 0x15 and self.root_verified and not body) or
                   (kind in (0x18, 0x1a) and len(body) == 4 and body[:2] == b'\0\0' and int.from_bytes(body[2:], 'big') in self.announced))
        if not allowed:
            raise ValueError('Root operation not allowed')
        identifier = self.root_id
        self.root_id = self.root_id % 65535 + 1
        self.send(envelope(uarp(kind, identifier, body)))

    def initialized(self):
        return self.case_verified and (self.version_replies == self.version_frames or
                (self.version_frames == 2 and self.version_replies == 1 and self.unknown_bytes == 8 and self.model_after_frames == 2))

    def child(self, kind, body):
        now = self.clock()
        size = len(body) + 6
        while self.budget and now - self.budget[0][0] >= 60:
            self.budget.popleft()
        cleanup = kind == 9
        reserve = 0 if cleanup else 10
        if not (self.closed and self.root_verified and self.case_active and 1 in self.announced):
            raise ValueError('Case operation before verified target/closed lid')
        if len(self.budget) >= (120 if cleanup else 119) or sum(n for _, n in self.budget) + size + reserve > 4096 or self.unconfirmed + size + reserve > 112:
            raise ValueError('Case request budget exceeded')
        if cleanup:
            allowed = self.cleaning and self.accepted and not self.cleanup_sent and body == struct.pack('>HH', self.asset, 3)
        elif self.cleaning or self.error or self.pending:
            allowed = False
        elif kind == 1:
            allowed = not self.case_model_sent and self.version_frames < 2 and body == b'\0\x07'
        elif kind == 3:
            allowed = body == b'\0\0\0\x02' and ((self.case_version and not self.case_model_sent) or self.accepted)
        elif kind == 0x11:
            allowed = self.initialized() and self.offer is None and not self.accepted and body == b'MTIC' and (not self.solicited or self.receipt and now - self.last_solicit >= 1)
        elif kind == 0x0d:
            allowed = self.initialized() and self.offer == body and not self.accepted
        elif kind == 0x14:
            allowed = self.case_verified and self.solicited and not self.accepted and len(body) == 6 and body[:4] == b'MTIC'
        else:
            allowed = False
        if not allowed or not self.case_verified and self.init_bytes + size > 112:
            raise ValueError('Case operation not allowed')
        self.budget.append((now, size))
        self.init_bytes += size
        self.unconfirmed += size
        if kind == 1:
            self.version_frames += 1
        elif kind == 3:
            self.case_model_sent = True
            if not self.case_verified:
                self.model_after_frames = self.version_frames
        elif kind == 0x11:
            self.solicited, self.receipt, self.last_solicit = True, False, now
        elif kind == 0x0d:
            self.accepted = True  # mark BEFORE write: cleanup must cover a partial acknowledgement
            self.asset = int.from_bytes(body[6:8], 'big')
        elif kind == 9:
            self.cleanup_sent = True
        child_id, root_id = self.child_id, self.root_id
        self.child_id, self.root_id = child_id % 65535 + 1, root_id % 65535 + 1
        self.send(envelope(uarp(0x1b, root_id, b'\0\x01' + uarp(kind, child_id, body))))

    def pending_request(self, kind, body, name):
        self.child(kind, body)
        self.pending, self.pending_at = name, self.clock()

    def handle(self, message):
        kind, identifier, body = unpack(message)
        if kind in (0x17, 0x19):
            if len(body) != 2:
                raise ValueError('Malformed endpoint announcement')
            endpoint = int.from_bytes(body, 'big')
            if kind == 0x17:
                self.announced.add(endpoint)
            if endpoint in self.announced:
                self.root(0x18 if kind == 0x17 else 0x1a, b'\0\0' + body)
            if endpoint == 1:
                self.case_active = kind == 0x17
                if not self.case_active:
                    raise ValueError('Charging case became unreachable')
            return
        if kind == 0x16:
            if body != b'\0\0':
                raise ValueError('Endpoint discovery failed')
            return
        if kind == 2:
            if len(body) < 4 or body[:2] != b'\0\0' or not 5 <= int.from_bytes(body[2:4], 'big') <= 7:
                raise ValueError('Root VERSION rejected')
            self.root_version, self.root_pending, self.root_unanswered = True, False, 0
            self.next_root = self.clock() + 1
            if not self.root_model_sent:
                self.root(3, b'\0\0\0\x02')
                self.root_model_sent, self.root_model_at = True, self.clock()
            return
        if kind == 4 and self.root_model_sent and not self.root_verified:
            identity = model(body)
            if not identity.startswith('airpods pro') or 'case' in identity:
                raise ValueError('Connected earbud is not an identified AirPods Pro')
            self.root_verified = True
            return
        if kind != 0x1b:
            return
        if len(body) < 8:
            raise ValueError('Short downstream frame')
        if body[:2] != b'\0\x01' or not self.case_active:
            return
        child_kind, response_id, payload = unpack(body[2:])
        if child_kind == 5:
            if payload[:4] != b'MTIC':
                return  # Never acknowledge firmware, LOGS or another asset.
            if len(payload) != 30 or payload[4:6] != b'\0\x0a' or int.from_bytes(payload[6:8], 'big') in (0, 65535) or not 0 < int.from_bytes(payload[24:28], 'big') <= 65536:
                raise ValueError('Invalid MTIC offer')
            if not self.offer and not self.cleaning:
                self.offer = payload
            return
        if child_kind not in (2, 4, 7, 15, 18, 19):
            return
        if response_id in self.responses:
            raise ValueError('Replayed case response')
        self.responses.append(response_id)
        if child_kind == 15 and self.cleanup_sent:
            if payload != struct.pack('>HH', self.asset, 3):
                raise ValueError('Invalid cleanup receipt')
            self.cleanup_ack = True
            self.pending = None
            self.unconfirmed = self.unknown_bytes
            return
        if self.cleaning:
            return
        if child_kind == 18 and self.pending == 'solicit':
            if payload != b'\0\0\0\0MTIC':
                raise ValueError('Case diagnostic renewal rejected')
            self.receipt, self.pending, self.unconfirmed = True, None, self.unknown_bytes
        elif child_kind == 19 and self.solicited and not self.accepted:
            if len(payload) != 6 or payload[:4] != b'MTIC':
                raise ValueError('Malformed rejection')
            self.pending = None
            self.child(20, payload)
            raise ValueError('Case declined diagnostic session')
        elif child_kind == 2 and self.version_replies < self.version_frames:
            if len(payload) < 4 or payload[:2] != b'\0\0' or not 5 <= int.from_bytes(payload[2:4], 'big') <= 7:
                raise ValueError('Case VERSION rejected')
            self.case_version = True
            self.version_replies += 1
            self.unconfirmed = max(0, self.unconfirmed - 8)
            self.unknown_bytes = max(0, self.unknown_bytes - 8)
        elif child_kind == 4 and self.case_model_sent and not self.case_verified:
            identity = model(payload)
            if self.pending != 'model' or self.model_after_frames != self.version_frames or not identity.startswith('airpods') or 'charging case' not in identity:
                raise ValueError('Case identity did not match ordered setup')
            self.case_identity, self.case_verified, self.pending = identity, True, None
            self.unconfirmed = max(0, self.unconfirmed - 10)
            self.unknown_bytes = (self.version_frames - self.version_replies) * 8
            if self.unknown_bytes != self.unconfirmed or self.unknown_bytes > 8:
                raise ValueError('Unanswered case setup budget exceeded')
        elif child_kind == 4 and self.case_verified and self.pending == 'identity':
            if model(payload) != self.case_identity:
                raise ValueError('Charging case identity changed')
            self.pending, self.unconfirmed = None, self.unknown_bytes
        elif child_kind == 4 and self.case_verified and not self.pending:
            return
        else:
            raise ValueError('Unexpected case reply')

    def tick(self):
        now = self.clock()
        if self.cleaning:
            return
        if self.root_pending and now - self.root_at >= 8:
            if self.root_unanswered >= (3 if self.root_version else 20):
                raise TimeoutError('Earbud VERSION heartbeat timed out')
        elif self.root_pending or now < self.next_root:
            pass
        if (not self.root_pending and now >= self.next_root) or self.root_pending and now - self.root_at >= 8:
            self.root(1, b'\0\x07')
            self.root_pending, self.root_at = True, now
            self.root_unanswered += 1
        if self.root_model_sent and not self.root_verified and now - self.root_model_at >= 8:
            raise TimeoutError('Earbud identity timed out')
        if self.root_verified and not self.discovery:
            self.root(21)
            self.discovery = True
        if self.pending and now - self.pending_at >= 5:
            if self.pending == 'identity':
                self.pending, self.unconfirmed = None, self.unknown_bytes
            else:
                raise TimeoutError('Case ' + self.pending + ' timed out')
        if self.pending or not (self.closed and self.root_verified and self.case_active):
            return
        if not self.case_verified:
            if self.case_version and not self.case_model_sent:
                self.pending_request(3, b'\0\0\0\x02', 'model')
            elif not self.case_model_sent and self.version_frames < 2 and now >= self.next_case_version:
                self.child(1, b'\0\x07')
                self.next_case_version = now + 8
            return
        if not self.initialized():
            raise ValueError('Case setup replies are incomplete')
        if self.offer is not None and not self.accepted:
            self.child(13, self.offer)
            self.next_identity = now + 1
        elif self.offer is None and (not self.solicited or self.receipt and now - self.last_solicit >= 1):
            self.pending_request(17, b'MTIC', 'solicit')
        elif self.accepted and now >= self.next_identity:
            self.pending_request(3, b'\0\0\0\x02', 'identity')
            self.next_identity = now + 1

    def cleanup(self):
        self.cleaning = True
        if self.accepted and self.case_active and not self.cleanup_sent:
            self.child(9, struct.pack('>HH', self.asset, 3))
