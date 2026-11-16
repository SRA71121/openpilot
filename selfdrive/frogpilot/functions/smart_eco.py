"""
Smart Eco Cruise - core logic (Phase 2/3: monitoring only).

This module NEVER commands the vehicle. It selects a speed-based eco profile,
estimates (or reads) battery power, compares it to the profile's power target,
and computes a *recommended* acceleration ceiling for future evaluation.

Pure Python with no openpilot imports so it can be unit tested off-device.
All tunables come from JSON stored in Params ("SmartEcoProfiles", "SmartEcoModel");
missing or invalid JSON falls back to the defaults below.
"""
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional

MPH_TO_MS = 0.44704
G = 9.81

# ---------------------------------------------------------------------------
# Defaults (all overridable via params)
# ---------------------------------------------------------------------------

DEFAULT_PROFILES = {
  "hysteresis_mph": 2.0,        # band edge must be crossed by this much to switch
  "target_rate_kw_s": 2.0,      # how fast the active target may move between profiles
  "over_target_margin_kw": 1.0, # power must exceed target by this much to count as "over"
  "profiles": [
    {"name": "Residential", "min_mph": 0,  "min_kw": 4.0,  "max_kw": 5.0},
    {"name": "Local",       "min_mph": 20, "min_kw": 10.0, "max_kw": 12.0},
    {"name": "County",      "min_mph": 40, "min_kw": 12.0, "max_kw": 16.0},
    {"name": "Highway",     "min_mph": 55, "min_kw": 18.0, "max_kw": 25.0},
    {"name": "High-speed",  "min_mph": 70, "min_kw": 25.0, "max_kw": 32.0},  # vehicle-specific; tune
  ],
}

# 2022 Chevy Bolt EV starting point. mass_kg of None -> use CarParams mass.
DEFAULT_MODEL = {
  "mass_kg": None,
  "payload_kg": 90.0,        # driver + typical cargo
  "cda_m2": 0.72,            # Cd ~0.31 x frontal area ~2.33 m^2
  "crr": 0.009,              # rolling resistance coefficient
  "air_density": 1.0,        # kg/m^3; ~1.0 at Colorado Front Range elevation
  "drive_efficiency": 0.88,  # battery -> wheel when motoring
  "regen_efficiency": 0.70,  # wheel -> battery when regenerating
  "aux_kw": 0.4,             # baseline accessory load (12V, pumps); HVAC not included
  "measured_current_sign": 0,  # 0 = learn automatically; 1 or -1 to force
}


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

@dataclass
class Profile:
  name: str
  min_ms: float
  min_kw: float
  target_kw: float  # band maximum = the ceiling everything is compared against


@dataclass
class EcoConfig:
  profiles: List[Profile]
  hysteresis_ms: float
  target_rate_kw_s: float
  over_target_margin_kw: float
  model: dict = field(default_factory=dict)


def _merge(defaults: dict, raw) -> dict:
  out = dict(defaults)
  if isinstance(raw, (bytes, str)) and raw:
    try:
      loaded = json.loads(raw)
      if isinstance(loaded, dict):
        out.update({k: v for k, v in loaded.items() if k in defaults})
    except (ValueError, TypeError):
      pass
  return out


def _profile(item: dict) -> Profile:
  hi = float(item["max_kw"])
  lo = float(item.get("min_kw", hi))
  return Profile(str(item["name"]), float(item["min_mph"]) * MPH_TO_MS, min(lo, hi), hi)


def parse_config(profiles_raw=None, model_raw=None) -> EcoConfig:
  p = _merge(DEFAULT_PROFILES, profiles_raw)
  m = _merge(DEFAULT_MODEL, model_raw)

  profiles = []
  try:
    for item in p["profiles"]:
      profiles.append(_profile(item))
  except (KeyError, TypeError, ValueError):
    profiles = []
  if not profiles:
    profiles = [_profile(i) for i in DEFAULT_PROFILES["profiles"]]
  profiles.sort(key=lambda x: x.min_ms)
  profiles[0].min_ms = 0.0  # lowest band always starts at 0

  return EcoConfig(
    profiles=profiles,
    hysteresis_ms=max(0.0, float(p["hysteresis_mph"])) * MPH_TO_MS,
    target_rate_kw_s=max(0.1, float(p["target_rate_kw_s"])),
    over_target_margin_kw=max(0.0, float(p["over_target_margin_kw"])),
    model=m,
  )


# ---------------------------------------------------------------------------
# Profile selection with hysteresis
# ---------------------------------------------------------------------------

class ProfileSelector:
  def __init__(self, profiles: List[Profile], hysteresis_ms: float):
    self.profiles = profiles
    self.h = hysteresis_ms
    self.idx: Optional[int] = None

  def _band(self, v):
    idx = 0
    for i, p in enumerate(self.profiles):
      if v >= p.min_ms:
        idx = i
    return idx

  def update(self, v_ego: float) -> int:
    if self.idx is None:
      self.idx = self._band(v_ego)
      return self.idx
    # step up while clearly above the next band's lower edge
    while self.idx + 1 < len(self.profiles) and v_ego >= self.profiles[self.idx + 1].min_ms + self.h:
      self.idx += 1
    # step down while clearly below the current band's lower edge
    while self.idx > 0 and v_ego < self.profiles[self.idx].min_ms - self.h:
      self.idx -= 1
    return self.idx


# ---------------------------------------------------------------------------
# Power model
# ---------------------------------------------------------------------------

class PowerModel:
  def __init__(self, model: dict, car_mass_kg: float):
    mass = model.get("mass_kg") or car_mass_kg
    self.m = float(mass) + float(model["payload_kg"])
    self.cda = float(model["cda_m2"])
    self.crr = float(model["crr"])
    self.rho = float(model["air_density"])
    self.eta_d = min(max(float(model["drive_efficiency"]), 0.5), 1.0)
    self.eta_r = min(max(float(model["regen_efficiency"]), 0.0), 1.0)
    self.aux_kw = float(model["aux_kw"])

  def road_load_w(self, v: float, pitch: float = 0.0) -> float:
    """Steady-state tractive power at the wheels (W). pitch in radians, nose-up positive."""
    v = max(v, 0.0)
    aero = 0.5 * self.rho * self.cda * v ** 3
    roll = self.crr * self.m * G * math.cos(pitch) * v if v > 0.1 else 0.0
    grade = self.m * G * math.sin(pitch) * v
    return aero + roll + grade

  def wheel_power_w(self, v: float, a: float, pitch: float = 0.0) -> float:
    return self.m * a * max(v, 0.0) + self.road_load_w(v, pitch)

  def battery_power_kw(self, v: float, a: float, pitch: float = 0.0) -> float:
    pw = self.wheel_power_w(v, a, pitch)
    pb = pw / self.eta_d if pw >= 0 else pw * self.eta_r
    return pb / 1000.0 + self.aux_kw

  def accel_for_power(self, target_kw: float, v: float, pitch: float = 0.0) -> float:
    """Acceleration (m/s^2) that would draw target_kw from the battery at speed v. Recommendation only."""
    v_eff = max(v, 2.0)  # avoid divide-by-zero / absurd values near standstill
    wheel_w = max(target_kw - self.aux_kw, 0.0) * 1000.0 * self.eta_d
    return (wheel_w - self.road_load_w(v, pitch)) / (self.m * v_eff)


# ---------------------------------------------------------------------------
# Measured power (HV pack V x I), with automatic sign detection
# ---------------------------------------------------------------------------

class MeasuredPower:
  """Tracks HV pack power when the car broadcasts it. Sign convention of the
  current signal is not documented for every platform, so it's learned by
  correlating against the model estimate during clear motoring/regen events."""
  TIMEOUT_S = 1.0
  MIN_EVIDENCE = 200       # samples (~10 s at 20 Hz) of |estimate| > threshold
  EVIDENCE_KW = 5.0

  def __init__(self, fixed_sign: int = 0):
    self.voltage = 0.0
    self.current = 0.0
    self.last_t: Optional[float] = None
    self.fixed_sign = fixed_sign
    self._corr = 0.0
    self._n = 0

  def update(self, t: float, voltage: float, current: float):
    self.voltage, self.current, self.last_t = voltage, current, t

  def available(self, t: float) -> bool:
    return self.last_t is not None and (t - self.last_t) < self.TIMEOUT_S and self.voltage > 50.0

  @property
  def sign(self) -> int:
    if self.fixed_sign in (-1, 1):
      return self.fixed_sign
    if self._n < self.MIN_EVIDENCE:
      return 0  # unknown yet
    return 1 if self._corr >= 0 else -1

  def raw_kw(self) -> float:
    return self.voltage * self.current / 1000.0

  def learn(self, estimate_kw: float):
    if abs(estimate_kw) > self.EVIDENCE_KW:
      self._corr += estimate_kw * self.raw_kw()
      self._n += 1

  def kw(self) -> Optional[float]:
    s = self.sign
    return None if s == 0 else s * self.raw_kw()


# ---------------------------------------------------------------------------
# Top-level monitor
# ---------------------------------------------------------------------------

@dataclass
class EcoInputs:
  t: float                 # monotonic seconds
  v_ego: float             # m/s
  a_ego: float             # m/s^2
  pitch: float = 0.0       # rad, nose-up positive
  pitch_valid: bool = False
  gas_pressed: bool = False
  long_active: bool = False


@dataclass
class EcoOutputs:
  profile_idx: int = 0
  profile_name: str = ""
  profile_min_kw: float = 0.0
  profile_target_kw: float = 0.0
  target_kw: float = 0.0
  estimated_kw: float = 0.0
  drive_kw: float = 0.0          # propulsion only (estimate minus baseline accessory load)
  measured_kw: Optional[float] = None
  power_kw: float = 0.0
  road_load_kw: float = 0.0
  over_target: bool = False
  driver_override: bool = False
  recommended_max_accel: float = 0.0
  grade_pct: float = 0.0
  trip_energy_kwh: float = 0.0
  trip_excess_kwh: float = 0.0
  trip_distance_km: float = 0.0
  trip_over_target_s: float = 0.0


class SmartEcoMonitor:
  def __init__(self, config: EcoConfig, car_mass_kg: float, measured: Optional[MeasuredPower] = None):
    self.cfg = config
    self.selector = ProfileSelector(config.profiles, config.hysteresis_ms)
    self.model = PowerModel(config.model, car_mass_kg)
    self.measured = measured
    self.target_kw: Optional[float] = None
    self.last_t: Optional[float] = None
    self.out = EcoOutputs()

  def reconfigure(self, config: EcoConfig, car_mass_kg: float):
    """Apply new settings mid-drive without losing trip totals."""
    self.cfg = config
    self.selector = ProfileSelector(config.profiles, config.hysteresis_ms)
    self.model = PowerModel(config.model, car_mass_kg)
    if self.measured is not None:
      self.measured.fixed_sign = int(config.model.get("measured_current_sign") or 0)

  def update(self, inp: EcoInputs) -> EcoOutputs:
    o = self.out
    dt = 0.0 if self.last_t is None else min(max(inp.t - self.last_t, 0.0), 0.5)
    self.last_t = inp.t

    # Profile + smoothed target
    o.profile_idx = self.selector.update(inp.v_ego)
    prof = self.cfg.profiles[o.profile_idx]
    o.profile_name = prof.name
    o.profile_min_kw = prof.min_kw
    o.profile_target_kw = prof.target_kw
    if self.target_kw is None:
      self.target_kw = prof.target_kw
    else:
      step = self.cfg.target_rate_kw_s * dt
      self.target_kw += min(max(prof.target_kw - self.target_kw, -step), step)
    o.target_kw = self.target_kw

    # Power
    pitch = inp.pitch if inp.pitch_valid else 0.0
    o.grade_pct = math.tan(pitch) * 100.0
    o.estimated_kw = self.model.battery_power_kw(inp.v_ego, inp.a_ego, pitch)
    o.drive_kw = o.estimated_kw - self.model.aux_kw
    o.road_load_kw = self.model.road_load_w(inp.v_ego, pitch) / 1000.0
    o.measured_kw = None
    if self.measured is not None and self.measured.available(inp.t):
      self.measured.learn(o.estimated_kw)
      o.measured_kw = self.measured.kw()
    o.power_kw = o.measured_kw if o.measured_kw is not None else o.estimated_kw

    # Comparison + recommendation (no actuation)
    o.over_target = o.power_kw > o.target_kw + self.cfg.over_target_margin_kw
    o.driver_override = inp.gas_pressed and o.over_target
    o.recommended_max_accel = self.model.accel_for_power(o.target_kw, inp.v_ego, pitch)

    # Trip accumulators
    o.trip_energy_kwh += o.power_kw * dt / 3600.0
    o.trip_excess_kwh += max(o.power_kw - o.target_kw, 0.0) * dt / 3600.0
    o.trip_distance_km += max(inp.v_ego, 0.0) * dt / 1000.0
    if o.over_target:
      o.trip_over_target_s += dt
    return o
