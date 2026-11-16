#!/usr/bin/env python3
"""python3 selfdrive/frogpilot/functions/tests/test_smart_eco_12v.py"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from smart_eco_12v import Battery12VLog, REST_AFTER_S  # noqa: E402


def feed(log, t0, seconds, volts, driving, step=1.0):
  t = t0
  while t < t0 + seconds:
    log.add(t, volts(t - t0) if callable(volts) else volts, driving)
    t += step
  return t


class Test12V(unittest.TestCase):
  def test_cadence_and_resting(self):
    log = Battery12VLog()
    t = feed(log, 0, 3600, 14.1, True, step=1.0)                 # 1 h drive @ DC-DC voltage
    onroad = len(log.samples)
    self.assertTrue(55 <= onroad <= 62)
    t = feed(log, t, 6 * 3600, lambda dt: 12.9 - min(dt, 3600) / 3600 * 0.4, False, step=5.0)  # parked, settling
    rest = log.resting()
    self.assertTrue(rest)
    self.assertGreaterEqual(rest[0][0], 3600 + REST_AFTER_S - 1)   # surface charge ignored
    self.assertAlmostEqual(log.latest_resting(), 12.5, places=2)

  def test_pre_drive_and_low_warning(self):
    log = Battery12VLog()
    t = feed(log, 0, 1800, 14.0, True, step=10)
    t = feed(log, t, 10 * 3600, 12.05, False, step=30)           # weak overnight
    self.assertEqual(log.low(12.2), 12.05)
    self.assertIsNone(log.low(12.0))
    feed(log, t, 600, 14.0, True, step=10)                       # next morning's drive
    pd = log.pre_drive()
    self.assertEqual(len(pd), 1)
    self.assertAlmostEqual(pd[0][1], 12.05)

  def test_garbage_and_storage(self):
    log = Battery12VLog()
    self.assertFalse(log.add(0, 0.0, False))
    self.assertTrue(log.add(0, 12.6, False))
    path = os.path.join(tempfile.mkdtemp(), "12v.json")
    log.save(path)
    self.assertEqual(Battery12VLog.load(path).samples, log.samples)
    self.assertEqual(Battery12VLog.load(path + "missing").samples, [])


if __name__ == "__main__":
  unittest.main()
