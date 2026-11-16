#!/usr/bin/env python3
"""Unit tests for Smart Eco Cruise core logic. Runs without the openpilot build:
  python3 selfdrive/frogpilot/functions/tests/test_smart_eco.py
"""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from smart_eco import (MPH_TO_MS, DEFAULT_PROFILES, EcoInputs, MeasuredPower, PowerModel,  # noqa: E402
                       ProfileSelector, SmartEcoMonitor, parse_config)

BOLT_MASS = 1669.0


def mph(x):
  return x * MPH_TO_MS


class TestConfig(unittest.TestCase):
  def test_defaults(self):
    cfg = parse_config()
    self.assertEqual([p.name for p in cfg.profiles], ["Residential", "Local", "County", "Highway", "High-speed"])
    self.assertEqual(cfg.profiles[3].min_kw, 18.0)
    self.assertEqual(cfg.profiles[3].target_kw, 25.0)

  def test_bad_json_falls_back(self):
    for raw in [b"not json", b"[]", b'{"profiles": "x"}', b'{"profiles": []}', None, b""]:
      cfg = parse_config(raw, raw)
      self.assertEqual(len(cfg.profiles), len(DEFAULT_PROFILES["profiles"]))

  def test_custom_profiles_sorted_and_zeroed(self):
    raw = json.dumps({"profiles": [{"name": "B", "min_mph": 30, "max_kw": 15},
                                   {"name": "A", "min_mph": 5, "max_kw": 7}]})
    cfg = parse_config(raw)
    self.assertEqual([p.name for p in cfg.profiles], ["A", "B"])
    self.assertEqual(cfg.profiles[0].min_ms, 0.0)
    self.assertEqual(cfg.profiles[0].min_kw, 7)  # min defaults to max when omitted


class TestHysteresis(unittest.TestCase):
  def setUp(self):
    cfg = parse_config()
    self.sel = ProfileSelector(cfg.profiles, cfg.hysteresis_ms)  # 2 mph

  def test_initial_band(self):
    self.assertEqual(self.sel.update(mph(45)), 2)

  def test_no_chatter_at_threshold(self):
    self.sel.update(mph(35))
    seq = [self.sel.update(mph(v)) for v in (39.5, 40.5, 41.0, 39.0, 40.9, 38.5)]
    self.assertTrue(all(i == 1 for i in seq), seq)

  def test_switch_up_and_down(self):
    self.sel.update(mph(35))
    self.assertEqual(self.sel.update(mph(42.1)), 2)
    self.assertEqual(self.sel.update(mph(38.5)), 2)  # inside hysteresis, hold
    self.assertEqual(self.sel.update(mph(37.9)), 1)

  def test_big_jump(self):
    self.sel.update(mph(10))
    self.assertEqual(self.sel.update(mph(75)), 4)
    self.assertEqual(self.sel.update(mph(5)), 0)


class TestPowerModel(unittest.TestCase):
  def setUp(self):
    self.m = PowerModel(parse_config().model, BOLT_MASS)

  def test_cruise_power_plausible(self):
    # Steady 65 mph on flat ground for a Bolt should be in the mid-teens of kW
    p = self.m.battery_power_kw(mph(65), 0.0)
    self.assertTrue(12 < p < 20, p)
    # Steady 20 mph is small
    self.assertLess(self.m.battery_power_kw(mph(20), 0.0), 4)

  def test_regen_negative(self):
    self.assertLess(self.m.battery_power_kw(mph(40), -1.5), 0)

  def test_grade_adds_power(self):
    flat = self.m.battery_power_kw(mph(50), 0.0)
    up = self.m.battery_power_kw(mph(50), 0.0, math.atan(0.05))
    self.assertGreater(up - flat, 15)  # 5% grade at 50 mph is a big load

  def test_accel_for_power_roundtrip(self):
    v = mph(45)
    a = self.m.accel_for_power(16.0, v)
    self.assertAlmostEqual(self.m.battery_power_kw(v, a), 16.0, places=3)


class TestMeasuredPower(unittest.TestCase):
  def test_timeout_and_sign_learning(self):
    mp = MeasuredPower()
    self.assertFalse(mp.available(0.0))
    # Car reports negative current while motoring (sign = -1)
    for i in range(250):
      t = i * 0.05
      mp.update(t, 350.0, -40.0)
      self.assertTrue(mp.available(t))
      mp.learn(14.0)
    self.assertEqual(mp.sign, -1)
    self.assertAlmostEqual(mp.kw(), 14.0)
    self.assertFalse(mp.available(250 * 0.05 + 2.0))

  def test_unknown_sign_until_evidence(self):
    mp = MeasuredPower()
    mp.update(0.0, 350.0, 10.0)
    mp.learn(2.0)  # below evidence threshold
    self.assertIsNone(mp.kw())


class TestMonitor(unittest.TestCase):
  def run_seq(self, mon, speeds_accels, dt=0.05, gas=False):
    t, out = 0.0, None
    for v, a in speeds_accels:
      out = mon.update(EcoInputs(t=t, v_ego=v, a_ego=a, gas_pressed=gas))
      t += dt
    return out

  def test_target_smoothing(self):
    mon = SmartEcoMonitor(parse_config(), BOLT_MASS)
    self.run_seq(mon, [(mph(50), 0.0)] * 5)
    self.assertEqual(mon.out.target_kw, 16.0)
    out = self.run_seq(mon, [(mph(58), 0.0)])  # jumps to Highway (25 kW)
    self.assertEqual(out.profile_name, "Highway")
    self.assertLess(out.target_kw, 16.5)  # rate-limited, not stepped
    out = self.run_seq(mon, [(mph(58), 0.0)] * 200)  # 10 s at 2 kW/s
    self.assertAlmostEqual(out.target_kw, 25.0)

  def test_override_and_excess(self):
    mon = SmartEcoMonitor(parse_config(), BOLT_MASS)
    out = self.run_seq(mon, [(mph(45), 0.0)] * 20)
    self.assertFalse(out.over_target)
    out = self.run_seq(mon, [(mph(45), 2.0)] * 20, gas=True)  # hard acceleration
    self.assertTrue(out.over_target)
    self.assertTrue(out.driver_override)
    self.assertGreater(out.trip_excess_kwh, 0)
    self.assertGreater(out.trip_over_target_s, 0)

  def test_measured_preferred_when_available(self):
    mp = MeasuredPower(fixed_sign=1)
    mon = SmartEcoMonitor(parse_config(), BOLT_MASS, mp)
    mp.update(0.0, 360.0, 50.0)  # 18 kW
    out = mon.update(EcoInputs(t=0.0, v_ego=mph(60), a_ego=0.0))
    self.assertAlmostEqual(out.power_kw, 18.0)
    out = mon.update(EcoInputs(t=5.0, v_ego=mph(60), a_ego=0.0))  # stale -> estimate
    self.assertIsNone(out.measured_kw)
    self.assertAlmostEqual(out.power_kw, out.estimated_kw)


if __name__ == "__main__":
  unittest.main()
