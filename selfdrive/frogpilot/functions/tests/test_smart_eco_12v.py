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
    ts, v, rest_min, short = log.readings[0][:4]
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


class TestStatus(unittest.TestCase):
  def _log(self, readings):
    from smart_eco_12v import Battery12VLog
    return Battery12VLog([[t * 86400.0, v, 480, 0] for t, v in readings])

  def test_status_levels(self):
    from smart_eco_12v import STATUS_OK, STATUS_LOW, STATUS_REPEAT
    self.assertEqual(self._log([]).status(12.2), STATUS_OK)
    self.assertEqual(self._log([(0, 12.6)]).status(12.2), STATUS_OK)
    self.assertEqual(self._log([(0, 12.6), (1, 12.1)]).status(12.2), STATUS_LOW)
    # low, charged, low again within 14 days -> repeat
    self.assertEqual(self._log([(0, 12.1), (1, 12.7), (5, 12.0)]).status(12.2), STATUS_REPEAT)
    # charged since -> clears even with history
    self.assertEqual(self._log([(0, 12.1), (5, 12.0), (6, 12.6)]).status(12.2), STATUS_OK)
    # earlier low too long ago -> just low
    self.assertEqual(self._log([(0, 12.1), (20, 12.7), (30, 12.0)]).status(12.2), STATUS_LOW)

  def test_short_rest_readings_ignored(self):
    from smart_eco_12v import Battery12VLog, STATUS_LOW
    log = Battery12VLog([[0.0, 11.9, 10, 1], [86400.0, 12.0, 480, 0]])
    self.assertEqual(log.status(12.2), STATUS_LOW)


class TestColdAndDrop(unittest.TestCase):
  def test_cold_status(self):
    from smart_eco_12v import Battery12VLog, STATUS_COLD, STATUS_LOW, STATUS_REPEAT
    # comma read 5 C at the reading -> ~-3 C cabin after self-heat -> cold
    self.assertEqual(Battery12VLog([[0.0, 12.0, 360, 0, 5.0, None]]).status(12.2), STATUS_COLD)
    self.assertEqual(Battery12VLog([[0.0, 12.0, 360, 0, 15.0, None]]).status(12.2), STATUS_LOW)
    self.assertEqual(Battery12VLog([[0.0, 12.0, 360, 0]]).status(12.2), STATUS_LOW)  # old 4-field reading
    # repeat wins over cold
    self.assertEqual(Battery12VLog([[0.0, 12.0, 360, 0, 5.0, None], [86400.0, 12.0, 360, 0, 5.0, None]]).status(12.2), STATUS_REPEAT)

  def _park(self, volts_at, hours=6.0, temp=10.0):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = 0.0
    for _ in range(30):            # driving
      log.add(t, 14.1, True); t += 60
    park = t
    while t - park < hours * 3600:
      log.add(t, volts_at((t - park) / 3600.0), False, temp); t += 60
    log.add(t, 14.1, True)         # next drive commits it
    return log

  def test_healthy_battery_no_drop_warning(self):
    log = self._park(lambda h: 12.62 - 0.01 * h)
    self.assertIsNotNone(log.readings[-1][5])
    self.assertIsNone(log.drop(0.10))

  def test_draining_battery_flags_drop(self):
    log = self._park(lambda h: 12.6 - 0.12 * max(0.0, h - 0.5))
    d = log.drop(0.10)
    self.assertIsNotNone(d)
    self.assertAlmostEqual(d, 0.24 - 0.01, delta=0.02)

  def test_surface_charge_first_30_min_not_counted(self):
    # big early fall from surface charge, then flat: must not flag
    log = self._park(lambda h: 12.62 + max(0.0, 0.5 - h) * 0.8)
    self.assertIsNone(log.drop(0.10))

  def test_short_park_has_no_drop_test(self):
    log = self._park(lambda h: 12.5, hours=2.0)
    self.assertIsNone(log.readings[-1][5])

  def test_charging_restarts_drop_test(self):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = 0.0
    log.add(t, 14.1, True); t += 60
    park = t
    while t - park < 3600:
      log.add(t, 12.6, False, 10.0); t += 60
    while t - park < 3 * 3600:     # plugged in / charging for 2 h
      log.add(t, 14.3, False, 10.0); t += 60
    rest = t
    while t - rest < 1.5 * 3600:   # only 1.5 h of rest after charging: no full drop test yet
      log.add(t, 12.3, False, 10.0); t += 60
    log.add(t, 14.1, True)
    self.assertIsNone(log.readings[-1][5])


class TestRiseAndHistory(unittest.TestCase):
  def test_topoff_below_charging_threshold_restarts_test(self):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = 0.0
    log.add(t, 14.1, True); t += 1
    park = t
    while t - park < 3 * 3600:
      h = (t - park) / 3600.0
      v = 12.6 - 0.12 * max(0.0, h - 0.5)      # draining...
      if 1.0 <= h < 1.0 + 300 / 3600:          # ...hidden by a 5-minute 13.3 V top-off
        v = 13.3
      log.add(t, v, False, 10.0); t += 1
    self.assertGreaterEqual(log.restarts, 1)
    log.add(t, 14.1, True)
    self.assertIsNone(log.readings[-1][5])     # no full 2 h of untouched rest after the top-off

  def test_noise_does_not_restart(self):
    import random
    from smart_eco_12v import Battery12VLog
    random.seed(1)
    log = Battery12VLog()
    t = 0.0
    log.add(t, 14.1, True); t += 1
    park = t
    while t - park < 3 * 3600:
      log.add(t, 12.6 + random.uniform(-0.02, 0.02), False, 10.0); t += 1
    self.assertEqual(log.restarts, 0)

  def test_history_and_summaries(self):
    import tempfile
    from smart_eco_12v import add_install, load_history, battery_summaries, current_install_t, Battery12VLog, STATUS_OK
    d = tempfile.mkdtemp() + "/h.json"
    day = 86400.0
    add_install(0 * day, "Lead-acid (flooded)", "OEM", d)
    add_install(400 * day, "LiFePO4", "", d)
    self.assertEqual(current_install_t(d), 400 * day)
    readings = [[10 * day, 12.6, 360, 0, 10.0, 0.02], [390 * day, 12.0, 360, 0, 10.0, 0.2], [410 * day, 13.3, 360, 0, 10.0, 0.01]]
    rows = battery_summaries(load_history(d), readings, 12.2, 0.10, 420 * day)
    self.assertEqual([r["type"] for r in rows], ["LiFePO4", "Lead-acid (flooded)"])
    self.assertEqual(rows[1]["days"], 400.0)
    self.assertEqual(rows[1]["low_count"], 1)
    self.assertEqual(rows[1]["drain_count"], 1)
    self.assertTrue(rows[0]["current"])
    # warnings start fresh for the new battery
    log = Battery12VLog([[390 * day, 12.0, 360, 0, 10.0, 0.2]])
    log.installed_t = 400 * day
    self.assertEqual(log.status(12.2), STATUS_OK)
    self.assertIsNone(log.drop(0.10))


class TestDailyHold(unittest.TestCase):
  def _drive(self, log, t, minutes=30):
    for _ in range(minutes * 60):
      log.add(t, 14.1, True); t += 1
    return t

  def test_holds_until_two_hour_test_done_then_once_a_day(self):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = self._drive(log, 0.0)
    park, held, released_at = t, [], None
    while t - park < 3 * 3600:
      v = 14.0 if t - park < 60 else 12.6     # DC-DC winding down right after parking: must not cancel
      log.add(t, v, False, 10.0)
      log.note_test_done(t)
      h = log.hold_wanted(t)
      held.append(h)
      if not h and released_at is None and t - park > 600:
        released_at = t - park
      t += 1
    self.assertTrue(held[700])
    self.assertIsNotNone(released_at)
    self.assertAlmostEqual(released_at / 3600, 2.0, delta=0.05)   # whole test = 2 h
    # same day, next park: no hold
    t = self._drive(log, t)
    log.add(t, 12.6, False, 10.0)
    self.assertFalse(log.hold_wanted(t + 60))
    # ~a day later: holds again
    t = self._drive(log, t + 20 * 3600)
    log.add(t + 1, 12.6, False, 10.0)
    self.assertTrue(log.hold_wanted(t + 61))

  def test_plugging_in_cancels_todays_test(self):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = self._drive(log, 0.0)
    park = t
    while t - park < 45 * 60:
      log.add(t, 12.6, False, 10.0); t += 1
    self.assertTrue(log.hold_wanted(t))
    for _ in range(600):                      # plugged in: DC-DC up
      log.add(t, 14.3, False, 10.0); t += 1
    for _ in range(3 * 3600):                 # unplugged again later the same day
      log.add(t, 12.6, False, 10.0); t += 1
      self.assertFalse(log.hold_wanted(t))

  def test_driving_releases_hold_and_short_stop_reading_not_trusted(self):
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog()
    t = self._drive(log, 0.0)
    for _ in range(20 * 60):                  # 20-minute store stop
      log.add(t, 12.6, False, 10.0); t += 1
    self.assertTrue(log.hold_wanted(t))
    log.add(t, 14.1, True)
    self.assertFalse(log.hold_wanted(t + 1))
    self.assertEqual(log.readings[-1][3], 1)  # short rest

  def test_saved_state_survives_reboot(self):
    import tempfile
    from smart_eco_12v import Battery12VLog
    log = Battery12VLog(last_test_t=1000.0, skip_until_t=2000.0)
    p = tempfile.mkdtemp() + "/12v.json"
    log.save(p)
    back = Battery12VLog.load(p)
    self.assertEqual((back.last_test_t, back.skip_until_t), (1000.0, 2000.0))


if __name__ == "__main__":
  unittest.main()
