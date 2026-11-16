#!/usr/bin/env python3
"""python3 selfdrive/frogpilot/functions/tests/test_smart_eco_12v.py"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from smart_eco_12v import Battery12VLog  # noqa: E402

H = 3600.0


def feed(log, t0, seconds, volts, driving, step=1.0):
  t = t0
  while t < t0 + seconds:
    log.add(t, volts(t - t0) if callable(volts) else volts, driving)
    t += step
  return t


class Test12V(unittest.TestCase):
  def test_one_reading_per_park_taken_last(self):
    log = Battery12VLog()
    t = feed(log, 0, H, 14.1, True)                                       # drive: nothing recorded
    self.assertIsNone(log.pending)
    t = feed(log, t, 6 * H, lambda dt: 12.9 - min(dt, 2 * H) / (2 * H) * 0.4, False, step=10)  # parked 6 h, settling
    self.assertEqual(log.readings, [])                                    # not recorded until the next drive
    feed(log, t, 600, 14.1, True)                                         # next drive starts
    self.assertEqual(len(log.readings), 1)
    ts, v, rest_min, short = log.readings[0]
    self.assertAlmostEqual(v, 12.5, places=2)                             # the LAST parked value
    self.assertGreater(rest_min, 355)
    self.assertEqual(short, 0)

  def test_reading_survives_power_off(self):
    path = os.path.join(tempfile.mkdtemp(), "12v.json")
    log = Battery12VLog()
    t = feed(log, 0, 600, 14.0, True, step=10)
    t = feed(log, t, 3 * H, 12.45, False, step=30)
    log.save(path)                                                        # comma shuts itself off here
    log2 = Battery12VLog.load(path)                                       # next morning: boots with the car
    log2.add(t + 10 * H, 14.0, True)
    self.assertEqual(len(log2.readings), 1)
    self.assertAlmostEqual(log2.readings[0][1], 12.45)
    self.assertGreater(log2.readings[0][2], 170)

  def test_charging_and_short_rest(self):
    log = Battery12VLog()
    t = feed(log, 0, 600, 14.0, True, step=10)
    t = feed(log, t, 2 * H, 14.3, False, step=30)                         # plugged in: DC-DC on, all skipped
    self.assertIsNone(log.pending)
    t = feed(log, t, 10 * 60, 12.7, False, step=30)                       # only 10 min since charging stopped
    feed(log, t, 60, 14.0, True)
    self.assertEqual(log.readings[0][3], 1)                               # surface charge: flagged short rest
    self.assertLess(log.readings[0][2], 11)
    log2 = Battery12VLog()
    t = feed(log2, 0, 600, 14.0, True, step=10)
    t = feed(log2, t, 10 * 60, 12.8, False, step=30)                      # 10 min stop
    feed(log2, t, 60, 14.0, True)
    self.assertEqual(log2.readings[0][3], 1)                              # flagged short rest
    self.assertIsNone(log2.latest())                                      # and not trusted

  def test_low_warning_uses_latest_trusted(self):
    log = Battery12VLog()
    t = 0.0
    for v in (12.6, 12.5, 12.1):
      t = feed(log, t, 600, 14.0, True, step=10)
      t = feed(log, t, 4 * H, v, False, step=60)
    feed(log, t, 60, 14.0, True)
    self.assertEqual(log.low(12.2), 12.1)
    self.assertIsNone(log.low(12.0))

  def test_garbage(self):
    log = Battery12VLog()
    self.assertFalse(log.add(0, 0.0, False))
    self.assertEqual(Battery12VLog.load("/nonexistent/12v.json").readings, [])


if __name__ == "__main__":
  unittest.main()
