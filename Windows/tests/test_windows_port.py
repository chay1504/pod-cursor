from pathlib import Path
import collections
import math
import struct
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Windows'))
from protocol import HEADER,Reader,Session,envelope,uarp,unpack,sensor_setting
from taps import Taps


def identity(name):
    data=name.encode()
    return struct.pack('>HII',0,2,len(data))+data


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.sent=[]
        self.session=Session(self.sent.append,lambda:self.now)
        self.reply_id=1000

    def reply(self,kind,body):
        self.reply_id+=1
        self.session.handle(uarp(27,300,b'\0\x01'+uarp(kind,self.reply_id,body)))

    def verified(self):
        s=self.session
        s.tick();s.handle(uarp(2,10,b'\0\0\0\x07'))
        s.handle(uarp(4,11,identity('AirPods Pro 3')));s.tick()
        s.handle(uarp(23,12,b'\0\x01'));s.closed=True;s.tick()
        self.reply(2,b'\0\0\0\x07');s.tick()
        self.reply(4,identity('AirPods Charging Case'));s.tick()
        self.reply(18,b'\0\0\0\0MTIC')
        return s

    def test_closed_case_lifecycle_and_scoped_release(self):
        s=self.verified()
        self.assertTrue(s.initialized())
        offer=bytearray(30);offer[:4]=b'MTIC'
        struct.pack_into('>HH',offer,4,10,7);struct.pack_into('>I',offer,24,40)
        self.reply(5,bytes(offer));s.tick()
        self.assertTrue(s.accepted)
        self.now+=1.1;s.tick();self.reply(4,identity('AirPods Charging Case'))
        s.cleanup();self.assertTrue(s.cleanup_sent)
        self.reply(15,struct.pack('>HH',7,3));self.assertTrue(s.cleanup_ack)
        child_types=[unpack(unpack(p[8:])[2][2:])[0] for p in self.sent if unpack(p[8:])[0]==27]
        self.assertNotIn(6,child_types) # never asks for asset DATA
        self.assertIn(13,child_types);self.assertIn(9,child_types)

    def test_renewal_requires_receipt_and_one_second(self):
        s=self.verified();count=len(self.sent)
        s.tick();self.assertEqual(len(self.sent),count)
        self.now+=1.1;s.tick();self.assertEqual(s.pending,'solicit')
        self.now+=1.1;count=len(self.sent);s.tick()
        # Root heartbeat may run, but no second child solicitation without a receipt.
        self.assertEqual(sum(unpack(p[8:])[0]==27 for p in self.sent[:count]),sum(unpack(p[8:])[0]==27 for p in self.sent))

    def test_wrong_root_model_blocks_discovery(self):
        s=self.session;s.tick();s.handle(uarp(2,1,b'\0\0\0\x07'))
        with self.assertRaises(ValueError):s.handle(uarp(4,2,identity('AirPods Charging Case')))
        self.assertFalse(s.root_verified)

    def test_wrong_case_blocks_diagnostics(self):
        s=self.session;s.root_verified=True;s.root_version=True;s.announced.add(1);s.case_active=True;s.closed=True
        s.case_version=True;s.version_frames=s.version_replies=1;s.tick()
        with self.assertRaises(ValueError):self.reply(4,identity('Other headphones'))
        self.assertFalse(s.solicited)

    def test_no_case_writes_before_closed_lid(self):
        s=self.session;s.root_verified=True;s.case_active=True;s.announced.add(1)
        with self.assertRaises(ValueError):s.child(1,b'\0\x07')

    def test_unknown_operation_never_written(self):
        s=self.verified();count=len(self.sent)
        for kind in (6,8,22,99):
            with self.assertRaises(ValueError):s.child(kind,b'\0'*4)
        self.assertEqual(len(self.sent),count)

    def test_duplicate_response_stops(self):
        s=self.verified()
        with self.assertRaises(ValueError):self.session.handle(uarp(27,900,b'\0\x01'+uarp(18,self.reply_id,b'\0\0\0\0MTIC')))

    def test_bad_offer_rejected(self):
        self.verified()
        with self.assertRaises(ValueError):self.reply(5,b'MTIC'+b'\0'*26)

    def test_rejected_diagnostic_request_stops(self):
        s=self.verified();self.now+=1.1;s.tick()
        with self.assertRaises(ValueError):self.reply(18,b'\0\0\0\x01MTIC')

    def test_case_reply_timeout(self):
        s=self.verified();self.now+=1.1;s.tick();self.now+=5.1
        with self.assertRaises(TimeoutError):s.tick()

    def test_partial_offer_ack_still_marks_cleanup_required(self):
        s=self.verified();offer=bytearray(30);offer[:4]=b'MTIC'
        struct.pack_into('>HH',offer,4,10,9);struct.pack_into('>I',offer,24,100)
        self.reply(5,bytes(offer))
        def fail(packet):raise OSError('partial write')
        s.send=fail
        with self.assertRaises(OSError):s.tick()
        self.assertTrue(s.accepted);s.send=self.sent.append;s.cleanup();self.assertTrue(s.cleanup_sent)

    def test_case_request_budget(self):
        s=self.verified();s.budget.extend([(self.now,10)]*119)
        with self.assertRaises(ValueError):s.child(3,b'\0\0\0\x02')


class ReaderTests(unittest.TestCase):
    def test_fragmented_raw_report_and_uarp(self):
        report=bytearray(28);report[0]=1
        struct.pack_into('<iii',report,1,100,-200,300);struct.pack_into('<Q',report,20,123456)
        nested=bytes([8,11,26,28])+report
        body=bytes([58,len(nested)])+nested
        packet=HEADER+bytes.fromhex('170000001000')+struct.pack('<H',len(body))+body
        for cut in range(len(packet)+1):
            reader=Reader();a,b=reader.feed(packet[:cut],1);c,d=reader.feed(packet[cut:],1)
            rows=a+c;self.assertEqual(len(rows),1);self.assertEqual(rows[0][2],123456);self.assertEqual(rows[0][4:],[100,-200,300])
        reader=Reader();frame=envelope(uarp(2,3,b'\0\0\0\x07'))
        self.assertEqual(reader.feed(frame,1)[1],[frame[8:]])

    def test_sensor_command_rejects_unknown_services(self):
        with self.assertRaises(ValueError):sensor_setting(16,5000,8001)
        with self.assertRaises(ValueError):sensor_setting(11,1234,8001)

    def test_duplicate_samples_are_not_motion(self):
        report=bytearray(28);report[0]=1;struct.pack_into('<Q',report,20,123456)
        nested=bytes([8,12,26,28])+report;body=bytes([58,len(nested)])+nested
        packet=HEADER+bytes.fromhex('170000001000')+struct.pack('<H',len(body))+body
        reader=Reader();self.assertEqual(len(reader.feed(packet,1)[0]),1);self.assertEqual(reader.feed(packet,2)[0],[])

    def test_bounds_and_malformed_frames(self):
        with self.assertRaises(ValueError):Reader().feed(b'x'*262145,1)
        with self.assertRaises(ValueError):unpack(b'\0'*4)
        with self.assertRaises(ValueError):Reader().feed(HEADER+b'\x4f\0\xff\xff',1)


class RecordedTapTests(unittest.TestCase):
    def test_original_recorded_fixtures(self):
        segments=collections.defaultdict(list)
        for line in (ROOT/'Tests/TapFixtures.csv').read_text().splitlines():
            if not line.strip() or line.startswith('#'):continue
            name,service,stamp,x,y,z=line.split(',')
            segments[name].append([0,int(service),int(stamp),0,int(x),int(y),int(z)])
        counts={}
        for name,rows in segments.items():
            detector=Taps();events=[]
            for i in range(0,len(rows),5):events.extend(detector.feed(rows[i:i+5]))
            counts[name]=len(events)
        self.assertIn(counts['held'],(14,15))
        for name,count in counts.items():
            if not name.startswith('tap') and name not in ('held','lidclose'):self.assertEqual(count,0,name)

    def test_original_javascript_orientation(self):
        result=subprocess.run(['node',str(ROOT/'Windows/orientation.mjs'),'--self-test'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('4 offline checks passed',result.stdout)


if __name__=='__main__':unittest.main()
