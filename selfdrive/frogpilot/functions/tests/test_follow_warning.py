import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from follow_warning import FollowWarning, HOLD_S, COOLDOWN_S

MPH = 0.44704
DT = 0.01


def run(fw, seconds, **kw):
  args = dict(enabled=True, v_ego=60 * MPH, lead_status=True, d_rel=15.0, gap_s=1.0,
              min_speed=25 * MPH, blinker=False, standstill=False)
  args.update(kw)
  fired = 0
  for _ in range(int(round(seconds / DT))):
    fired += fw.update(DT, **args)
  return fired


class TestFollowWarning(unittest.TestCase):
  def test_fires_after_hold(self):
    fw = FollowWarning()
    self.assertEqual(run(fw, HOLD_S - 0.1), 0)  # 15 m at 60 mph = 0.56 s gap, not yet held long enough
    self.assertEqual(run(fw, 0.2), 1)

  def test_safe_gap_never_fires(self):
    self.assertEqual(run(FollowWarning(), 60, d_rel=40.0), 0)  # 1.5 s at 60 mph

  def test_brief_tailgate_does_not_fire(self):
    fw = FollowWarning()
    for _ in range(10):
      run(fw, 1.5)
      run(fw, 0.5, d_rel=40.0)
    self.assertEqual(fw.cooldown, 0.0)

  def test_cooldown_limits_repeats(self):
    fw = FollowWarning()
    self.assertEqual(run(fw, COOLDOWN_S + HOLD_S + 0.5), 2)  # once, then again after the cooldown

  def test_suppressed_cases(self):
    for kw in ({"blinker": True}, {"standstill": True}, {"lead_status": False},
               {"enabled": False}, {"v_ego": 20 * MPH, "d_rel": 3.0}, {"d_rel": 0.5}):
      self.assertEqual(run(FollowWarning(), 10, **kw), 0, kw)

  def test_min_speed_zero_still_needs_motion(self):
    self.assertEqual(run(FollowWarning(), 10, min_speed=0.0, v_ego=0.2, d_rel=2.0), 0)


if __name__ == "__main__":
  unittest.main()
