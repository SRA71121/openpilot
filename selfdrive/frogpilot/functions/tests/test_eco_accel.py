"""User-set Eco acceleration: the 0-30 and 30-60 mph times the driver picks are what the car does."""
import importlib.util
import os
import sys
import types
import unittest

for name, attrs in (("openpilot.common.params", {"Params": object}), ("openpilot.system.hardware", {"HARDWARE": None})):
  if name not in sys.modules:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod

_path = os.path.join(os.path.dirname(__file__), "..", "frogpilot_functions.py")
_spec = importlib.util.spec_from_file_location("frogpilot_functions_eco", _path)
ff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ff)
F = ff.FrogPilotFunctions


def drive(t30, t60, dt=0.01):
  scales = ff.eco_accel_scales(t30, t60)
  v = t = 0.0
  while v < ff.ECO_SPLIT_MS:
    v += F.get_max_accel_eco(v, *scales) * dt
    t += dt
  first = t
  while v < ff.ECO_TOP_MS:
    v += F.get_max_accel_eco(v, *scales) * dt
    t += dt
  return first, t - first


class TestEcoAccel(unittest.TestCase):
  def test_defaults_match_gentle_eco(self):
    a, b = drive(20, 45)
    self.assertAlmostEqual(a, 20, delta=1.0)
    self.assertAlmostEqual(b, 45, delta=1.5)

  def test_user_times_are_hit(self):
    for t30, t60 in ((8, 15), (15, 30), (30, 60), (40, 90)):
      a, b = drive(t30, t60)
      self.assertAlmostEqual(a, t30, delta=max(1.0, 0.05 * t30), msg=(t30, t60, a))
      self.assertAlmostEqual(b, t60, delta=max(1.5, 0.05 * t60), msg=(t30, t60, b))

  def test_mixed_settings_close(self):
    a, b = drive(10, 60)
    self.assertAlmostEqual(a, 10, delta=1.0)
    self.assertAlmostEqual(b, 60, delta=3.0)

  def test_missing_or_silly_values_are_safe(self):
    self.assertEqual(ff.eco_accel_scales(0, 0), ff.eco_accel_scales(20, 45))
    hi = ff.eco_accel_scales(1, 1)  # clamped to the fastest allowed settings
    self.assertEqual(hi, ff.eco_accel_scales(8, 15))
    for v in (0, 5, 13, 20, 30):
      self.assertLessEqual(F.get_max_accel_eco(v, *hi), 2.0)
      self.assertGreater(F.get_max_accel_eco(v, *ff.eco_accel_scales(40, 90)), 0.0)

  def test_no_step_at_30_mph(self):
    s = ff.eco_accel_scales(10, 90)
    prev = F.get_max_accel_eco(ff.ECO_SPLIT_MS - 3, *s)
    v = ff.ECO_SPLIT_MS - 3
    while v < ff.ECO_SPLIT_MS + 3:
      v += 0.1
      cur = F.get_max_accel_eco(v, *s)
      self.assertLess(abs(cur - prev), 0.05)
      prev = cur


if __name__ == "__main__":
  unittest.main()
