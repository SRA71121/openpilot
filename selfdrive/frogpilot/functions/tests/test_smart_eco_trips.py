#!/usr/bin/env python3
"""python3 selfdrive/frogpilot/functions/tests/test_smart_eco_trips.py"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import smart_eco_trips as st  # noqa: E402

HOME = (40.3978, -105.0750)   # Loveland-ish
WORK = (40.0500, -105.2700)   # Boulder-ish


def drive(t, start, end, mph=55, kw=10.0, minutes=40, measured_extra=None):
  v = mph / st.MPH
  n = int(minutes * 60 / 0.05)
  for i in range(n):
    f = i / n
    pos = (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)
    meas = None if measured_extra is None else kw + measured_extra
    t.update(0.05, v, 0.0, kw, meas, max(kw - 12, 0), kw > 12, pos)
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
    self.assertIsNone(s["accessory_kwh"])
    rows = st.speed_table([t.bins])
    self.assertEqual(rows[0]["range"], "55-60")
    self.assertAlmostEqual(rows[0]["steady_kw"], 10.0, places=3)

  def test_heat_split(self):
    t = drive(st.TripLog(), HOME, WORK, kw=10.0, minutes=30, measured_extra=3.0)
    s = t.summary()
    self.assertAlmostEqual(s["accessory_kwh"], 1.5, delta=0.02)
    self.assertAlmostEqual(s["drive_mi_per_kwh"], s["miles"] / s["drive_kwh"])  # heat not counted

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
    self.assertIsNotNone(by["Winter"]["avg_heat_kwh"])

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
