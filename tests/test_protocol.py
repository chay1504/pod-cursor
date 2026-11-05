import math
import json
import plistlib
from pathlib import Path
import random
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import Decoder, WX, block_sample, fields, wx_command, rh_command


def block():
    data = bytearray(58)
    data[0] = 1
    struct.pack_into('<Q', data, 1, 1_000_000_000)
    struct.pack_into('<hhh', data, 26, 100, -200, 0)
    struct.pack_into('<hhh', data, 38, 300, 0, 0)
    struct.pack_into('<hhh', data, 44, 0, 0, -1000)
    return bytes(data)


def wx_packet(data, service=16):
    inner = bytes([8, service, 26, len(data)]) + data
    body = bytes([58, len(inner)]) + inner
    return WX + struct.pack('<H', len(body)) + body


class ProtocolTests(unittest.TestCase):
    def test_known_block_units(self):
        sample = block_sample(block(), 'test')
        self.assertAlmostEqual(sample.t, 1)
        self.assertAlmostEqual(sample.gyro[0], math.radians(12.2))
        self.assertEqual(sample.gravity, (0., 0., -1.))
        self.assertAlmostEqual(sample.accel[0], .3)

    def test_sensor_packet_and_unknown_service(self):
        samples, commands = Decoder().decode(wx_packet(block()))
        self.assertEqual(len(samples), 1)
        self.assertEqual(commands, [])
        self.assertEqual(Decoder().decode(wx_packet(block(), 88)), ([], []))

    def test_truncation_is_rejected(self):
        packet = wx_packet(block())
        for length in range(len(packet)):
            self.assertEqual(Decoder().decode(packet[:length]), ([], []))

    def test_malformed_protobuf_is_rejected(self):
        for malformed in [b'\x00', b'\xff' * 20, b'\x3a\xff\x7fshort']:
            packet = WX + struct.pack('<H', len(malformed)) + malformed
            self.assertEqual(Decoder().decode(packet), ([], []))

    def test_random_input_never_becomes_motion(self):
        rng = random.Random(42)
        for _ in range(500):
            data = rng.randbytes(rng.randrange(0, 200))
            self.assertEqual(Decoder().decode(data), ([], []))

    def test_invalid_motion_block_rejected(self):
        for bad in [b'', block()[:50], b'\0' * 58, block() + b'\0']:
            self.assertIsNone(block_sample(bad, 'test'))

    def test_start_stop_packets_have_valid_length(self):
        for interval in (20000, 0):
            packet = wx_command(16, interval)
            self.assertEqual(struct.unpack_from('<H', packet, 10)[0], len(packet) - 12)
            self.assertEqual(struct.unpack_from('<I', packet, len(packet) - 4)[0], interval)

    def test_remotehid_requires_discovery(self):
        decoder = Decoder()
        packet = rh_command(7, 2, b'\0' + block())
        self.assertEqual(decoder.decode(packet), ([], []))
        decoder.remote_devices.add(7)
        self.assertEqual(len(decoder.decode(packet)[0]), 1)

    def test_real_recorded_sensor_packets(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/recorded-motion.json').read_text(encoding='utf8'))
        self.assertEqual(len(fixture['packets']), 12)
        decoder = Decoder()
        decoder.remote_devices.add(7)
        decoded = []
        for item in fixture['packets']:
            samples, _ = decoder.decode(bytes.fromhex(item['packet']))
            self.assertEqual(len(samples), item['samples'])
            self.assertTrue(all(s.valid() for s in samples))
            decoded.extend(samples)
        self.assertEqual(len(decoded), 12)
        self.assertAlmostEqual(decoded[0].t, 7286.713575)
        self.assertEqual(decoded[0].gravity, (.675, -.055, -.769))

    def test_remotehid_discovery_and_malformed_xml(self):
        decoder = Decoder()
        xml = plistlib.dumps({'AccessoryService': 'devmotion6'})
        samples, commands = decoder.decode(rh_command(7, 0, xml))
        self.assertEqual(samples, [])
        self.assertEqual(len(commands), 1)
        self.assertIn(7, decoder.remote_devices)
        bad = b'<?xml version="1.0"?><plist><dict>broken</plist>'
        self.assertEqual(decoder.decode(rh_command(7, 0, bad)), ([], []))


if __name__ == '__main__':
    unittest.main()
