#!/usr/bin/env python3
"""python3 selfdrive/frogpilot/functions/tests/test_smart_eco_trips.py"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import smart_eco_trips as st  # noqa: E402

HOME = (40.3978, -105.0750)   # Loveland-ish
WORK = (40.0500, -105.2700)   # Boulder-ish


def drive(t, start, end, mph=55, kw=10.0, minutes=40, measured_extra=None, target=12.0):
  v = mph / st.MPH
  n = int(minutes * 60 / 0.05)
  for i in range(n):
    f = i / n
    pos = (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)
    meas = None if measured_extra is None else kw + measured_extra
    t.update(0.05, v, 0.0, kw, target, meas, pos)
  return t


class TestTrips(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()

  def test_summary_and_bins(self):
    t = drive(st.TripLog(1000.0), HOME, WORK, mph=57, kw=10.0, minutes=30)
    s = t.summary()
    self.assertAlmostEqual(s["miles"], 28.5, delta=0.2)
    self.assertAlmostEqual(s["drive_kwh"], 5.0, delta=0.05)
    self.assertAlmostEqual(s["drive_mi_per_kwh"], 5.7, delta=0.05)
    rows = st.speed_table([t.bins])
    self.assertEqual(rows[0]["range"], "55-60")
    self.assertAlmostEqual(rows[0]["steady_kw"], 10.0, places=3)
    self.assertEqual((rows[0]["steady_min_kw"], rows[0]["steady_max_kw"]), (10.0, 10.0))
    self.assertNotIn("accessory_kwh", s)

  def test_measured_is_plain_total(self):
    t = drive(st.TripLog(), HOME, WORK, kw=10.0, minutes=30, measured_extra=3.0)
    s = t.summary()
    self.assertAlmostEqual(s["measured_kwh"], 6.5, delta=0.02)          # shown as-is
    self.assertAlmostEqual(s["drive_mi_per_kwh"], s["miles"] / s["drive_kwh"])  # ranking ignores it

  def test_routes_and_leaderboard(self):
    for i, kw in enumerate((11.0, 9.5, 10.2)):
      st.finalize(drive(st.TripLog(1000.0 + i * 10000), HOME, WORK, kw=kw), self.dir)
    st.finalize(drive(st.TripLog(50000.0), WORK, HOME, kw=12.0), self.dir)   # reverse = separate route
    routes = st.load_routes(self.dir)
    self.assertEqual(len(routes), 2)
    boards = st.leaderboards(st.load_trips(self.dir), routes)
    first = [b for b in boards if b["route"]["id"] == 1][0]
    self.assertEqual(first["count"], 3)
    self.assertGreater(first["runs"][0]["drive_mi_per_kwh"], first["runs"][1]["drive_mi_per_kwh"])
    self.assertTrue(st.rename_route(1, "Home -> Work", self.dir))
    self.assertEqual(st.load_routes(self.dir)[0]["name"], "Home -> Work")

  def test_checkpoint_recovery_and_short_trips(self):
    t = drive(st.TripLog(7000.0), HOME, WORK, minutes=10)
    st.checkpoint(t, self.dir)
    rec = st.recover_unfinished(self.dir)
    self.assertIsNotNone(rec)
    self.assertFalse(os.path.exists(os.path.join(self.dir, "current.json")))
    self.assertIsNone(st.finalize(st.TripLog(8000.0), self.dir))  # zero-mile drive not stored

  def test_loop_drive_has_no_route(self):
    t = drive(st.TripLog(), HOME, HOME, minutes=5)
    self.assertIsNone(st.finalize(t, self.dir)["route_id"])



def seq(t, pieces, dt=0.05, target=16.0):
  """pieces: list of (seconds, mph_start, mph_end, kw, blinker)"""
  for secs, m0, m1, kw, blink in pieces:
    n = int(secs / dt)
    a = ((m1 - m0) / st.MPH) / secs if secs else 0.0
    for i in range(n):
      v = (m0 + (m1 - m0) * i / n) / st.MPH
      t.update(dt, v, a, kw, target, None, None, blink)
  return t


class TestEventsAndBalance(unittest.TestCase):
  def test_pass_hard_accel_hard_slow(self):
    t = st.TripLog(0.0)
    seq(t, [(60, 55, 55, 12, False),          # cruise
            (5, 55, 70, 60, True),            # pass with signal
            (60, 70, 55, -5, False),          # gentle coast back down
            (6, 20, 40, 45, False),           # hard accel, no signal
            (30, 40, 40, 8, False),
            (3, 40, 25, -35, False),          # hard slowing
            (30, 25, 25, 4, False)])
    t.finish()
    types = [e["type"] for e in t.events]
    self.assertEqual(types, ["pass", "hard acceleration", "hard slowing"])
    s = t.summary()
    self.assertEqual(s["event_count"], 3)
    # total includes events, clean excludes them -> clean is more efficient here
    self.assertGreater(s["clean_mi_per_kwh"], s["drive_mi_per_kwh"])
    self.assertGreater(t.events[0]["over_kwh"], 0)

  def test_short_blips_are_not_events(self):
    t = st.TripLog(0.0)
    seq(t, [(30, 50, 50, 10, False), (0.5, 50, 53, 60, False), (30, 53, 53, 10, False)])
    t.finish()
    self.assertEqual(t.events, [])

  def test_energy_balance(self):
    t = st.TripLog(0.0)
    seq(t, [(3600, 55, 55, 20, False)], target=16.0)    # 1 h at 4 kW over the ceiling
    seq(t, [(1800, 55, 55, -10, False)], target=16.0)   # 30 min regen at 10 kW
    s = t.summary()
    self.assertAlmostEqual(s["lost_kwh"], 4.0, places=2)
    self.assertAlmostEqual(s["won_back_kwh"], 5.0, places=2)
    self.assertAlmostEqual(s["net_kwh"], 1.0, places=2)

  def test_band_accel_regen_split_and_extremes(self):
    t = st.TripLog(0.0)
    seq(t, [(10, 50, 54, 30, False), (10, 54, 50, -12, False), (10, 52, 52, 9, False)])
    rows = st.speed_table([t.bins])
    r = [x for x in rows if x["range"] == "50-55"][0]
    self.assertAlmostEqual(r["accel_kw"], 30.0, places=3)
    self.assertAlmostEqual(r["slow_kw"], -12.0, places=3)
    self.assertGreater(r["regen_kwh"], 0)
    self.assertEqual(r["max_kw"], 30.0)
    self.assertEqual(r["min_kw"], -12.0)

  def test_roundtrip_keeps_events(self):
    t = st.TripLog(0.0)
    seq(t, [(6, 20, 40, 45, False), (5, 40, 40, 5, False)])
    t.finish()
    t2 = st.TripLog.from_dict(t.to_dict())
    self.assertEqual(t2.events, t.events)


class TestSeasonsJourneys(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()

  def test_season_split(self):
    import time as _t
    jul = _t.mktime((2026, 7, 10, 7, 0, 0, 0, 0, -1))
    jan = _t.mktime((2027, 1, 10, 7, 0, 0, 0, 0, -1))
    st.finalize(drive(st.TripLog(jul), HOME, WORK, kw=9.0), self.dir)
    st.finalize(drive(st.TripLog(jan), HOME, WORK, kw=12.0, measured_extra=3.0), self.dir)
    st.finalize(drive(st.TripLog(jan + 86400), HOME, WORK, kw=11.0, measured_extra=2.0), self.dir)
    rows = st.season_stats(st.load_trips(self.dir), st.load_routes(self.dir))
    by = {r["season"]: r for r in rows}
    self.assertEqual(by["Summer"]["runs"], 1)
    self.assertEqual(by["Winter"]["runs"], 2)
    self.assertGreater(by["Summer"]["avg_mi_per_kwh"], by["Winter"]["avg_mi_per_kwh"])
    self.assertNotIn("avg_heat_kwh", by["Winter"])

  def test_journeys(self):
    shop = (40.20, -105.10)
    t0 = 1_800_000_000.0
    a = drive(st.TripLog(t0), HOME, shop, minutes=15)
    b = drive(st.TripLog(a.end_epoch + 600), shop, WORK, minutes=20)     # 10 min stop -> same journey
    c = drive(st.TripLog(b.end_epoch + 7200), WORK, HOME, minutes=40)    # 2 h later -> separate
    for t in (a, b, c):
      st.finalize(t, self.dir)
    js = st.journeys(st.load_trips(self.dir), {})
    self.assertEqual(len(js), 1)
    self.assertEqual(js[0]["legs"], 2)
    self.assertAlmostEqual(js[0]["miles"], a.miles + b.miles, places=3)


if __name__ == "__main__":
  unittest.main()
