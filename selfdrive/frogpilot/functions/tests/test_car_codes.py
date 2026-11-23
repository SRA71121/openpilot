import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import car_codes as cc


class FakeParams:
  def __init__(self, d=None):
    self.d = dict(d or {})

  def get_bool(self, k):
    return self.d.get(k) in (True, "1", b"1")

  def remove(self, k):
    self.d.pop(k, None)

  def put(self, k, v):
    self.d[k] = v


class TestDecode(unittest.TestCase):
  def test_decode_letters(self):
    self.assertEqual(cc.decode_dtc(0x0A, 0x7F), "P0A7F")
    self.assertEqual(cc.decode_dtc(0x41, 0x23), "C0123")
    self.assertEqual(cc.decode_dtc(0x93, 0x25), "B1325")
    self.assertEqual(cc.decode_dtc(0xC1, 0x00), "U0100")

  def test_obd_with_count(self):
    # 0x43 stripped: count 2, P0A7F, U0100
    self.assertEqual(cc.parse_obd_dtcs(bytes([2, 0x0A, 0x7F, 0xC1, 0x00])), ["P0A7F", "U0100"])

  def test_obd_without_count_and_padding(self):
    self.assertEqual(cc.parse_obd_dtcs(bytes([0x0A, 0x7F, 0x00, 0x00])), ["P0A7F"])
    self.assertEqual(cc.parse_obd_dtcs(bytes([0])), [])

  def test_uds_records(self):
    payload = bytes([0xFF, 0x93, 0x25, 0x03, 0x09, 0xC1, 0x00, 0x00, 0x28])
    out = cc.parse_uds_dtcs(payload)
    self.assertEqual(out[0], {"code": "B1325", "ftb": "03", "status": "active"})
    self.assertEqual(out[1]["code"], "U0100")
    self.assertEqual(out[1]["status"], "stored")

  def test_gmlan_frames_dedupe_and_end(self):
    frames = [bytes([0x81, 0x93, 0x25, 0x03, 0x09, 0, 0, 0]),
              bytes([0x81, 0x93, 0x25, 0x03, 0x09, 0, 0, 0]),
              bytes([0x7F, 0xA9, 0x12, 0, 0, 0, 0, 0]),
              bytes([0x81, 0x00, 0x00, 0x00, 0x00, 0, 0, 0]),
              bytes([0x81, 0xC1, 0x00, 0x00, 0x08, 0, 0, 0])]
    out = cc.parse_gmlan_frames(frames)
    self.assertEqual([c["code"] for c in out], ["B1325"])

  def test_summary(self):
    self.assertIn("No modules", cc.summarize({"modules": []}))
    self.assertIn("No trouble codes", cc.summarize({"modules": [{"codes": []}]}))
    s = cc.summarize({"modules": [{"codes": [{"code": "P0A7F", "ftb": "", "status": "stored"}]}]})
    self.assertEqual(s, "1 code: P0A7F")
    self.assertIn("failed", cc.summarize({"error": "boom"}))


class TestStorageAndRequest(unittest.TestCase):
  def test_save_and_history_cap(self):
    with tempfile.TemporaryDirectory() as d:
      for i in range(cc.HISTORY_MAX + 5):
        cc.save_result({"time": i, "modules": [], "seconds": 1.0}, d)
      self.assertEqual(cc.load_latest(d)["time"], cc.HISTORY_MAX + 4)
      h = cc.load_history(d)
      self.assertEqual(len(h), cc.HISTORY_MAX)
      self.assertEqual(h[-1]["time"], cc.HISTORY_MAX + 4)

  def test_no_request_does_nothing(self):
    p = FakeParams()
    called = []
    cc.run_requested_scan(p, None, None, lambda *a: called.append(a))
    self.assertEqual(called, [])

  def test_scan_errors_never_raise_and_clear_request(self):
    p = FakeParams({"CarCodesRequest": True})
    def boom(*a):
      raise RuntimeError("no panda")
    cc.run_requested_scan(p, None, None, boom)  # must not raise
    self.assertNotIn("CarCodesRequest", p.d)  # cleared so a failure can't repeat every start


if __name__ == "__main__":
  unittest.main()
