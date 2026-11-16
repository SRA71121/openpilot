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
  "usable_kwh": 65.0,        # for "range at this pace"
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


def parse_config(profiles_raw=None, model_raw=None, band_overrides=None) -> EcoConfig:
  """band_overrides: optional list of (min_kw, max_kw) per band from the comma's settings screen.
  A value <= 0 means 'not set' and the JSON/default is kept."""
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
  for prof, ov in zip(profiles, band_overrides or []):
    try:
      lo, hi = float(ov[0]), float(ov[1])
    except (TypeError, ValueError, IndexError):
      continue
    if hi > 0:
      prof.target_kw = hi
      prof.min_kw = min(lo, hi) if lo > 0 else min(prof.min_kw, hi)

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

    # Comparison + recommendation (no actuation). Uses driving power only, never heater/accessory load.
    o.over_target = o.drive_kw > o.target_kw + self.cfg.over_target_margin_kw
    o.driver_override = inp.gas_pressed and o.over_target
    o.recommended_max_accel = self.model.accel_for_power(o.target_kw, inp.v_ego, pitch)

    # Trip accumulators
    o.trip_energy_kwh += o.drive_kw * dt / 3600.0
    o.trip_excess_kwh += max(o.drive_kw - o.target_kw, 0.0) * dt / 3600.0
    o.trip_distance_km += max(inp.v_ego, 0.0) * dt / 1000.0
    if o.over_target:
      o.trip_over_target_s += dt
    return o


# ---------------------------------------------------------------------------
# Optional speed control (only used by the planner when openpilot controls speed)
# ---------------------------------------------------------------------------

class EcoLongControl:
  """Power ceiling + highway glide. Only ever LOWERS the planner's max acceleration
  (never touches braking/min accel) and, for glide, lets the cruise target float a
  few mph above the set speed on descents. Pressing the gas disables both instantly."""
  LEAD_TIME_GAP = 3.0           # s: a lead closer than this (or slower than us) disables glide
  GLIDE_MIN_SPEED = 35 * MPH_TO_MS
  DOWNHILL_GRADE = -0.01        # -1%
  CAP_FLOOR = -0.3              # m/s^2: the ceiling may ease off, never brake hard

  def __init__(self, config: EcoConfig, car_mass_kg: float, limiter: bool = False, glide: bool = False,
               glide_band_mph: float = 3.0, sag_band_mph: float = 3.0):
    self.reconfigure(config, car_mass_kg, limiter, glide, glide_band_mph, sag_band_mph)
    self.state = "off"

  def reconfigure(self, config, car_mass_kg, limiter, glide, glide_band_mph, sag_band_mph):
    self.cfg = config
    self.model = PowerModel(config.model, car_mass_kg)
    self.selector = ProfileSelector(config.profiles, config.hysteresis_ms)
    self.limiter, self.glide = bool(limiter), bool(glide)
    self.glide_band = max(0.0, min(float(glide_band_mph), 5.0)) * MPH_TO_MS
    self.sag_band = max(0.0, min(float(sag_band_mph), 5.0)) * MPH_TO_MS

  def coast_accel(self, v: float, pitch: float = 0.0) -> float:
    """Acceleration the car has with zero motor power (drag + rolling + grade)."""
    v_eff = max(v, 2.0)
    return -self.model.road_load_w(v, pitch) / (self.model.m * v_eff)

  def update(self, v_ego, v_set, v_limit, pitch=0.0, lead_status=False, lead_d=200.0, lead_v=0.0, gas_pressed=False):
    """Returns (max_accel_cap or None, v_cruise_target or None)."""
    if gas_pressed or not (self.limiter or self.glide) or v_set <= 0:
      self.state = "override" if gas_pressed else "off"
      return None, None

    cap, v_target = None, None
    curve_limited = v_limit < v_set - 0.5
    lead_close = lead_status and (lead_d < max(30.0, v_ego * self.LEAD_TIME_GAP) or lead_v < v_ego - 1.0)
    self.state = "normal"

    if self.limiter and not curve_limited:
      prof = self.cfg.profiles[self.selector.update(v_ego)]
      cap = self.model.accel_for_power(prof.target_kw, v_ego, pitch)
      if v_ego < v_set - self.sag_band:
        cap = max(cap, 0.0)  # already sagged as far as allowed: at least hold speed
      cap = max(cap, self.CAP_FLOOR)
      self.state = "limit"

    if self.glide and v_ego >= self.GLIDE_MIN_SPEED and not lead_close and not curve_limited:
      downhill = math.tan(pitch) < self.DOWNHILL_GRADE
      if (downhill and v_ego >= v_set - 0.3) or v_ego > v_set + 0.1:
        v_target = v_set + self.glide_band
        coast = self.coast_accel(v_ego, pitch)
        cap = coast if cap is None else min(cap, coast)
        self.state = "glide"

    return cap, v_target


# ---------------------------------------------------------------------------
# Live efficiency score + range at this pace
# ---------------------------------------------------------------------------

def instant_score(drive_kw: float, target_kw: float) -> float:
  """0-10 for this instant. Inside the eco band ~8-10, over it drops, hard regen dips a little."""
  if drive_kw < 0:
    return 9.5 if drive_kw > -15 else max(6.0, 9.5 + (drive_kw + 15) * 0.15)
  r = drive_kw / max(target_kw, 1.0)
  pts = [(0.0, 10.0), (0.6, 10.0), (1.0, 8.0), (1.5, 5.0), (2.5, 1.0)]
  if r >= pts[-1][0]:
    return 1.0
  for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
    if r <= x1:
      return y0 + (y1 - y0) * (r - x0) / (x1 - x0)
  return 1.0


class EcoScore:
  TAU_S = 5.0          # score smoothing
  PACE_TAU_S = 180.0   # "range at this pace" looks at roughly the last few minutes

  def __init__(self, usable_kwh: float = 65.0):
    self.usable_kwh = usable_kwh
    self.score = None
    self.trip_sum = 0.0
    self.trip_t = 0.0
    self._mi = 0.0
    self._kwh = 0.0

  def update(self, dt: float, v: float, drive_kw: float, target_kw: float):
    if dt <= 0:
      return
    if v > 1.0:
      s = instant_score(drive_kw, target_kw)
      k = min(dt / self.TAU_S, 1.0)
      self.score = s if self.score is None else self.score + k * (s - self.score)
      self.trip_sum += self.score * dt
      self.trip_t += dt
    decay = math.exp(-dt / self.PACE_TAU_S)
    self._mi = self._mi * decay + max(v, 0.0) * dt / 1609.344
    self._kwh = self._kwh * decay + drive_kw * dt / 3600.0

  @property
  def trip_score(self):
    return self.trip_sum / self.trip_t if self.trip_t > 5 else None

  @property
  def pace_mi_per_kwh(self):
    return self._mi / self._kwh if self._kwh > 0.02 and self._mi > 0.2 else None

  @property
  def pace_range_mi(self):
    p = self.pace_mi_per_kwh
    return p * self.usable_kwh if p else None
