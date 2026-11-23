import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from follow_warning import FollowWarning, NONE, YELLOW, RED, HOLD_S, REARM_S

MPH = 0.44704
DT = 0.01


def args(**kw):
  a = dict(enabled=True, v_ego=60 * MPH, a_ego=0.0, lead_status=True, d_rel=22.0, v_lead=60 * MPH,
           gap_s=1.0, red_gap_s=0.6, min_speed=25 * MPH, blinker=False, standstill=False)
  a.update(kw)
  return a


def run(fw, seconds, **kw):
  """Returns the list of levels seen (one per tick)."""
  return [fw.update(DT, **args(**kw)) for _ in range(int(round(seconds / DT)))]


class TestFollowWarning(unittest.TestCase):
  def test_yellow_after_hold_then_clears(self):
    fw = FollowWarning()  # 22 m at 60 mph = 0.82 s: yellow zone, same speed so no closing
    levels = run(fw, HOLD_S + 0.2)
    self.assertEqual(levels[int((HOLD_S - 0.1) / DT)], NONE)
    self.assertEqual(levels[-1], YELLOW)
    self.assertEqual(run(fw, 0.1, d_rel=40.0)[-1], NONE)

  def test_safe_gap_never_fires(self):
    self.assertEqual(set(run(FollowWarning(), 60, d_rel=40.0)), {NONE})

  def test_red_by_gap(self):
    fw = FollowWarning()  # 12 m at 60 mph = 0.45 s
    levels = run(fw, 1.0, d_rel=12.0)
    self.assertEqual(levels[-1], RED)
    self.assertNotIn(YELLOW, levels)  # straight to red, no 2 s wait

  def test_closing_fast_goes_red_quickly(self):
    fw = FollowWarning()  # 1.2 s gap but 20 mph faster than the lead: impact in ~3.6 s -> fast, then red
    d = 32.0
    levels = []
    for _ in range(int(3.0 / DT)):
      levels.append(fw.update(DT, **args(d_rel=d, v_lead=40 * MPH)))
      d -= 20 * MPH * DT
    self.assertIn(YELLOW, levels)
    first_yellow = levels.index(YELLOW) * DT
    first_red = levels.index(RED) * DT
    self.assertLess(first_yellow, 1.0)
    self.assertLess(first_red - first_yellow, 1.0)

  def test_normal_stop_behind_traffic_stays_quiet(self):
    fw = FollowWarning()  # 45 mph toward stopped traffic 110 m ahead, braking 2 m/s^2 (stops with ~9 m to spare)
    v, d, levels = 45 * MPH, 110.0, []
    while v > 25 * MPH:
      levels.append(fw.update(DT, **args(v_ego=v, a_ego=-2.0, d_rel=d, v_lead=0.0)))
      d -= v * DT
      v -= 2.0 * DT
    self.assertNotIn(RED, levels)

  def test_hard_accel_skips_wait(self):
    fw = FollowWarning()
    levels = run(fw, 0.5, a_ego=2.0, v_lead=55 * MPH)
    self.assertEqual(levels[-1], YELLOW)

  def test_rearm_limits_repeats(self):
    fw = FollowWarning()
    run(fw, HOLD_S + 0.1)
    run(fw, 0.1, d_rel=40.0)
    self.assertNotIn(YELLOW, run(fw, REARM_S - 1.0))
    self.assertIn(YELLOW, run(fw, HOLD_S + 2.0))

  def test_red_steps_down_to_yellow(self):
    fw = FollowWarning()
    run(fw, 1.0, d_rel=12.0)
    self.assertEqual(run(fw, 0.1, d_rel=22.0)[-1], YELLOW)

  def test_suppressed_cases(self):
    for kw in ({"blinker": True}, {"standstill": True}, {"lead_status": False},
               {"enabled": False}, {"v_ego": 20 * MPH, "d_rel": 3.0}, {"d_rel": 0.5}):
      self.assertEqual(set(run(FollowWarning(), 10, **kw)), {NONE}, kw)

  def test_blinker_clears_active_alert(self):
    fw = FollowWarning()
    run(fw, 1.0, d_rel=12.0)
    self.assertEqual(run(fw, 0.05, d_rel=12.0, blinker=True)[-1], NONE)


if __name__ == "__main__":
  unittest.main()
