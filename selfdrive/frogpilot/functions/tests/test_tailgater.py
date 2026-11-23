import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tailgater as tg

DT = 0.05


class Clock:
  def __init__(self):
    self.t = 1000.0


def drive(sess, clock, seconds, requested=True, engaged=True, night=False, seg_fn=None, **kw):
  out = None
  for _ in range(int(round(seconds / DT))):
    seg = seg_fn(clock.t) if seg_fn else "2026-11-23--13-40-02--0"
    out = sess.update(clock.t, requested, engaged, night, seg, wall=clock.t, **kw)
    requested = out[1]
    clock.t += DT
  return out


def seg_by_minute(start):
  return lambda t: f"2026-11-23--13-40-02--{int((t - start) // 60)}"


class TestRamp(unittest.TestCase):
  def test_opens_gradually_and_never_below_base(self):
    f, steps = 0.0, 0
    while f < 2.5 - 1e-6:
      f = tg.ramp_follow(f, 1.45, 2.5, DT)
      steps += 1
      self.assertGreaterEqual(f, 1.45)
    self.assertAlmostEqual(steps * DT, (2.5 - 1.45) / tg.FOLLOW_RAMP, delta=0.1)  # ~10.5 s

  def test_release_hands_back(self):
    f = 3.0
    for _ in range(400):
      f = tg.ramp_follow(f, 1.45, 0.0, DT)
    self.assertAlmostEqual(f, 1.45)

  def test_base_bigger_than_target_wins(self):
    self.assertEqual(tg.ramp_follow(0.0, 2.8, 2.5, DT), 2.8)


class TestNight(unittest.TestCase):
  def test_hysteresis(self):
    n = tg.NightDetector()
    self.assertFalse(n.update(35))
    self.assertTrue(n.update(20))
    self.assertTrue(n.update(35))
    self.assertFalse(n.update(45))


class TestSession(unittest.TestCase):
  def test_day_and_night_targets(self):
    s, c = tg.TailgaterSession(), Clock()
    self.assertEqual(drive(s, c, 1)[0], tg.DAY_FOLLOW_S)
    self.assertEqual(drive(s, c, 1, night=True)[0], tg.NIGHT_FOLLOW_S)

  def test_tap_off_then_records_after_window(self):
    s, c = tg.TailgaterSession(), Clock()
    seg = seg_by_minute(c.t)
    drive(s, c, 90, seg_fn=seg, v_ego=27.0, lead_status=True, d_rel=40.0)
    target, req = drive(s, c, 0.1, requested=False, seg_fn=seg)
    self.assertEqual((target, req), (0.0, False))
    self.assertFalse(s.ready_to_save(c.t))
    drive(s, c, tg.AFTER_S + 1, requested=False, seg_fn=seg)
    self.assertTrue(s.ready_to_save(c.t))
    inc = s.take_incident()
    self.assertEqual(inc["segments"], [f"2026-11-23--13-40-02--{i}" for i in range(3)])  # during + minute after
    self.assertEqual(inc["end_reason"], "tapped off")
    self.assertAlmostEqual(inc["min_gap_s"], round(40 / 27, 2))
    self.assertEqual(inc["seconds"], 90)

  def test_retap_during_after_window_keeps_both(self):
    s, c = tg.TailgaterSession(), Clock()
    drive(s, c, 30)
    drive(s, c, 10, requested=False)
    drive(s, c, 30)
    self.assertTrue(s.ready_to_save(c.t))
    done = s.pop_finished(c.t)
    self.assertEqual(len(done), 1)
    self.assertEqual(done[0]["end_reason"], "tapped off")
    self.assertTrue(s.active)

  def test_time_limit(self):
    s, c = tg.TailgaterSession(), Clock()
    _, req = drive(s, c, tg.MAX_S + 1)
    self.assertFalse(req)
    self.assertFalse(s.active)
    self.assertEqual(s.incident["end_reason"], "time limit")

  def test_disengage_ends_only_if_it_was_engaged(self):
    s, c = tg.TailgaterSession(), Clock()
    drive(s, c, 5, engaged=False)  # Always On Lateral only: stays on
    self.assertTrue(s.active)
    drive(s, c, 5, engaged=True)
    _, req = drive(s, c, 0.1, engaged=False)
    self.assertFalse(req)
    self.assertEqual(s.incident["end_reason"], "disengaged")

  def test_car_off_mid_session(self):
    s, c = tg.TailgaterSession(), Clock()
    drive(s, c, 30)
    s.force_end(c.t, wall=c.t)
    self.assertTrue(s.ready_to_save(c.t))
    self.assertEqual(s.take_incident()["end_reason"], "car off")

  def test_storage_cap(self):
    with tempfile.TemporaryDirectory() as d:
      for i in range(tg.INCIDENT_MAX + 3):
        tg.save_incident({"start": i}, d)
      items = tg.load_incidents(d)
      self.assertEqual(len(items), tg.INCIDENT_MAX)
      self.assertEqual(items[-1]["start"], tg.INCIDENT_MAX + 2)

  def test_incident_links_include_minute_before(self):
    links = tg.incident_links(["r--3", "r--4"])
    self.assertEqual([l["seg"] for l in links], ["2", "3", "4"])
    self.assertEqual([l["seg"] for l in tg.incident_links(["r--0"])], ["0"])

  def test_segment_links(self):
    self.assertEqual(tg.segment_links("2026-11-23--13-40-02--5"), {"route": "2026-11-23--13-40-02", "seg": "5"})


if __name__ == "__main__":
  unittest.main()
