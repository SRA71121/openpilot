"""
Smart Eco Cruise - trip log, route leaderboards, events and speed-vs-power stats.

Pure Python (no openpilot imports) so it runs off-device in tests and inside the
Fleet Manager web page. Data lives in /data/smart_eco/ on the comma:
  trips/<start_epoch>.json   one file per finished drive
  current.json               checkpoint of the drive in progress
  routes.json                auto-detected repeat routes (start/end clusters) and their names

Energy terms (no guessing about the heater anywhere)
  drive_kwh     propulsion energy from the physics model, net of regen. Rankings use this
                TOTAL, events included.
  clean_kwh     drive energy with tagged events (hard accel / passing / hard slowing) removed.
  measured_kwh  the car's own pack reading (V x I) when it broadcasts one: a plain total,
                shown as-is with no attempt to split out where it went.
  won_back_kwh  energy recovered by regen.   lost_kwh  energy spent above your band ceilings.
"""
import json
import math
import os
import time
from typing import Dict, List, Optional, Tuple

DATA_DIR = "/data/smart_eco"
MPH = 2.23694           # m/s -> mph
MI_PER_M = 1 / 1609.344
BIN_MPH = 5
STEADY_ACCEL = 0.15     # |a| below this (m/s^2) counts as steady cruising
MIN_SCORED_MILES = 1.0
ROUTE_RADIUS_M = 400.0

# Event detection
EVENT_ACCEL = 0.8       # m/s^2 sustained -> hard acceleration
EVENT_POWER_X = 1.5     # or driving power above 1.5x the band ceiling (and above EVENT_MIN_KW)
EVENT_MIN_KW = 15.0
EVENT_DECEL = -1.5      # m/s^2 sustained -> hard slowing
EVENT_HOLD_S = 1.0      # condition must hold this long to count, and clear this long to end
PASS_MIN_MPH = 40.0     # hard acceleration with a turn signal at/above this speed = pass
MAX_EVENTS = 300


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
  lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
  h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371000.0 * math.asin(math.sqrt(h))


def _new_bin() -> dict:
  return {"t": 0.0, "kwh": 0.0,                         # everything in this band
          "st": 0.0, "skwh": 0.0,                       # steady cruising
          "at": 0.0, "akwh": 0.0,                       # accelerating
          "dt": 0.0, "dkwh": 0.0, "rkwh": 0.0,          # slowing: net energy, regen recovered (positive)
          "max_kw": None, "min_kw": None,               # extremes, any driving
          "smax_kw": None, "smin_kw": None}             # extremes while steady


def _ext(b, key_max, key_min, kw):
  b[key_max] = kw if b[key_max] is None else max(b[key_max], kw)
  b[key_min] = kw if b[key_min] is None else min(b[key_min], kw)


class TripLog:
  def __init__(self, start_epoch: Optional[float] = None):
    self.start_epoch = start_epoch if start_epoch is not None else time.time()
    self.end_epoch = self.start_epoch
    self.dist_m = 0.0
    self.time_s = 0.0
    self.moving_s = 0.0
    self.drive_kwh = 0.0
    self.measured_kwh = 0.0
    self.measured_s = 0.0
    self.won_back_kwh = 0.0
    self.lost_kwh = 0.0
    self.over_target_s = 0.0
    self.eco_score: Optional[float] = None
    self.start_pos: Optional[List[float]] = None
    self.end_pos: Optional[List[float]] = None
    self.bins: Dict[str, dict] = {}
    self.events: List[dict] = []
    self._ev: Optional[dict] = None   # event being tracked

  def update(self, dt: float, v: float, a: float, drive_kw: float, target_kw: float,
             measured_kw: Optional[float] = None, pos: Optional[Tuple[float, float]] = None, blinker: bool = False):
    if dt <= 0:
      return
    self.time_s += dt
    self.end_epoch = self.start_epoch + self.time_s
    self.dist_m += max(v, 0.0) * dt
    e = drive_kw * dt / 3600.0
    self.drive_kwh += e
    if drive_kw < 0:
      self.won_back_kwh += -e
    over = max(drive_kw - target_kw, 0.0)
    self.lost_kwh += over * dt / 3600.0
    if over > 0:
      self.over_target_s += dt
    if measured_kw is not None:
      self.measured_kwh += measured_kw * dt / 3600.0
      self.measured_s += dt
    if pos is not None:
      if self.start_pos is None:
        self.start_pos = [pos[0], pos[1]]
      self.end_pos = [pos[0], pos[1]]

    if v > 0.5:
      self.moving_s += dt
      b = self.bins.setdefault(str(int(v * MPH // BIN_MPH)), _new_bin())
      b["t"] += dt
      b["kwh"] += e
      _ext(b, "max_kw", "min_kw", drive_kw)
      if abs(a) < STEADY_ACCEL:
        b["st"] += dt
        b["skwh"] += e
        _ext(b, "smax_kw", "smin_kw", drive_kw)
      elif a > 0:
        b["at"] += dt
        b["akwh"] += e
      else:
        b["dt"] += dt
        b["dkwh"] += e
        if drive_kw < 0:
          b["rkwh"] += -e

    self._track_event(dt, v, a, drive_kw, target_kw, blinker)

  # --- events ---------------------------------------------------------------
  def _track_event(self, dt, v, a, drive_kw, target_kw, blinker):
    accel = a > EVENT_ACCEL or (drive_kw > max(EVENT_MIN_KW, EVENT_POWER_X * target_kw))
    slow = a < EVENT_DECEL
    kind = "accel" if accel else "slow" if slow else None
    ev = self._ev

    if ev is not None and (kind == ev["kind"] or (kind is None and ev["off"] + dt < EVENT_HOLD_S)):
      # still in (or only briefly out of) the event: keep accumulating
      if kind == ev["kind"]:
        ev["off"] = 0.0
        ev["on"] += dt
      else:
        ev["off"] += dt
      ev["s"] += dt
      ev["kwh"] += drive_kw * dt / 3600.0
      ev["over_kwh"] += max(drive_kw - target_kw, 0.0) * dt / 3600.0
      ev["mi"] += max(v, 0.0) * dt * MI_PER_M
      ev["peak_kw"] = max(ev["peak_kw"], drive_kw) if ev["kind"] == "accel" else min(ev["peak_kw"], drive_kw)
      ev["v1"] = v * MPH
      ev["blinker"] = ev["blinker"] or blinker
      return

    if ev is not None:
      self._close_event()
    if kind is not None:
      self._ev = {"kind": kind, "t": self.time_s - dt, "s": dt, "on": dt, "off": 0.0,
                  "kwh": drive_kw * dt / 3600.0, "over_kwh": max(drive_kw - target_kw, 0.0) * dt / 3600.0,
                  "mi": max(v, 0.0) * dt * MI_PER_M, "peak_kw": drive_kw, "v0": v * MPH, "v1": v * MPH,
                  "blinker": blinker}

  def _close_event(self):
    ev, self._ev = self._ev, None
    if ev is None or ev["on"] < EVENT_HOLD_S or len(self.events) >= MAX_EVENTS:
      return
    if ev["kind"] == "slow":
      typ = "hard slowing"
    elif ev["blinker"] and ev["v0"] >= PASS_MIN_MPH:
      typ = "pass"
    else:
      typ = "hard acceleration"
    self.events.append({"type": typ, "t": round(ev["t"], 1), "s": round(ev["s"], 1),
                        "v0": round(ev["v0"], 1), "v1": round(ev["v1"], 1), "kwh": round(ev["kwh"], 4),
                        "over_kwh": round(ev["over_kwh"], 4), "mi": round(ev["mi"], 4),
                        "peak_kw": round(ev["peak_kw"], 1)})

  def finish(self):
    """Close any event still open (call before saving a finished trip)."""
    if self._ev is not None:
      self._close_event()

  # --- derived numbers ------------------------------------------------------
  @property
  def miles(self) -> float:
    return self.dist_m * MI_PER_M

  def summary(self) -> dict:
    mi = self.miles
    ev_mi = sum(e["mi"] for e in self.events)
    ev_kwh = sum(e["kwh"] for e in self.events)
    clean_mi, clean_kwh = mi - ev_mi, self.drive_kwh - ev_kwh
    return {
      "start": self.start_epoch, "end": self.end_epoch, "miles": mi,
      "minutes": self.time_s / 60.0,
      "avg_mph": (mi / (self.moving_s / 3600.0)) if self.moving_s > 1 else 0.0,
      "drive_kwh": self.drive_kwh,
      "drive_mi_per_kwh": (mi / self.drive_kwh) if self.drive_kwh > 0.01 else None,
      "clean_kwh": clean_kwh,
      "clean_mi_per_kwh": (clean_mi / clean_kwh) if clean_kwh > 0.01 else None,
      "measured_kwh": self.measured_kwh if self.measured_s > 0 else None,
      "measured_coverage": self.measured_s / self.time_s if self.time_s > 0 else 0.0,
      "won_back_kwh": self.won_back_kwh,
      "lost_kwh": self.lost_kwh,
      "net_kwh": self.won_back_kwh - self.lost_kwh,
      "over_target_min": self.over_target_s / 60.0,
      "eco_score": self.eco_score,
      "event_count": len(self.events),
      "events": self.events,
    }

  _FIELDS = ("start_epoch", "end_epoch", "dist_m", "time_s", "moving_s", "drive_kwh", "measured_kwh", "measured_s",
             "won_back_kwh", "lost_kwh", "over_target_s", "eco_score", "start_pos", "end_pos", "bins", "events")

  def to_dict(self) -> dict:
    return {k: getattr(self, k) for k in self._FIELDS}

  @classmethod
  def from_dict(cls, d: dict) -> "TripLog":
    t = cls(d.get("start_epoch", 0.0))
    for k in cls._FIELDS:
      if k in d:
        setattr(t, k, d[k])
    # tolerate bins from an older format
    t.bins = {k: b for k, b in (t.bins or {}).items() if isinstance(b, dict)}
    t.events = t.events or []
    return t


def speed_table(bins_list: List[Dict[str, dict]]) -> List[dict]:
  """Combine bins from one or more trips into rows for the proof table."""
  merged: Dict[int, dict] = {}
  for bins in bins_list:
    for k, b in bins.items():
      if not isinstance(b, dict):
        continue
      m = merged.setdefault(int(k), _new_bin())
      for f in ("t", "kwh", "st", "skwh", "at", "akwh", "dt", "dkwh", "rkwh"):
        m[f] += b.get(f, 0.0)
      for f, fn in (("max_kw", max), ("smax_kw", max), ("min_kw", min), ("smin_kw", min)):
        if b.get(f) is not None:
          m[f] = b[f] if m[f] is None else fn(m[f], b[f])

  def avg(kwh, t):
    return kwh * 3600.0 / t if t > 0 else None

  rows = []
  for idx in sorted(merged):
    m = merged[idx]
    rows.append({
      "range": f"{idx * BIN_MPH}-{(idx + 1) * BIN_MPH}",
      "minutes": m["t"] / 60.0,
      "avg_kw": avg(m["kwh"], m["t"]) or 0.0,
      "steady_minutes": m["st"] / 60.0,
      "steady_kw": avg(m["skwh"], m["st"]),
      "steady_min_kw": m["smin_kw"], "steady_max_kw": m["smax_kw"],
      "accel_minutes": m["at"] / 60.0, "accel_kw": avg(m["akwh"], m["at"]),
      "slow_minutes": m["dt"] / 60.0, "slow_kw": avg(m["dkwh"], m["dt"]),
      "regen_kwh": m["rkwh"],
      "max_kw": m["max_kw"], "min_kw": m["min_kw"],
    })
  return rows


# --- storage -----------------------------------------------------------------

def _path(*p):
  return os.path.join(DATA_DIR, *p)


def _write_json(path: str, obj):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(obj, f)
  os.replace(tmp, path)


def _read_json(path: str, default):
  try:
    with open(path) as f:
      return json.load(f)
  except (OSError, ValueError):
    return default


def checkpoint(trip: TripLog, data_dir: str = DATA_DIR):
  _write_json(os.path.join(data_dir, "current.json"), trip.to_dict())


def finalize(trip: TripLog, data_dir: str = DATA_DIR) -> Optional[dict]:
  """Store a finished trip (if it's long enough to matter) and clear the checkpoint."""
  out = None
  trip.finish()
  if trip.miles >= 0.2:
    rec = trip.to_dict()
    rec["route_id"] = assign_route(trip.start_pos, trip.end_pos, data_dir)
    _write_json(os.path.join(data_dir, "trips", f"{int(trip.start_epoch)}.json"), rec)
    out = rec
  try:
    os.remove(os.path.join(data_dir, "current.json"))
  except OSError:
    pass
  return out


def recover_unfinished(data_dir: str = DATA_DIR) -> Optional[dict]:
  """A drive that ended without a clean shutdown left a checkpoint; store it now."""
  d = _read_json(os.path.join(data_dir, "current.json"), None)
  if not d:
    return None
  return finalize(TripLog.from_dict(d), data_dir)


def load_routes(data_dir: str = DATA_DIR) -> List[dict]:
  return _read_json(os.path.join(data_dir, "routes.json"), [])


def save_routes(routes: List[dict], data_dir: str = DATA_DIR):
  _write_json(os.path.join(data_dir, "routes.json"), routes)


def assign_route(start, end, data_dir: str = DATA_DIR) -> Optional[int]:
  """Match a trip to a known route by start AND end within ROUTE_RADIUS_M; create one if new."""
  if not start or not end:
    return None
  routes = load_routes(data_dir)
  for r in routes:
    if haversine_m(start, r["start"]) < ROUTE_RADIUS_M and haversine_m(end, r["end"]) < ROUTE_RADIUS_M:
      return r["id"]
  if haversine_m(start, end) < ROUTE_RADIUS_M:
    return None  # loop drive (errand from home and back) - not a route
  rid = max([r["id"] for r in routes], default=0) + 1
  routes.append({"id": rid, "name": f"Route {rid}", "start": list(start), "end": list(end)})
  save_routes(routes, data_dir)
  return rid


def rename_route(rid: int, name: str, data_dir: str = DATA_DIR) -> bool:
  routes = load_routes(data_dir)
  for r in routes:
    if r["id"] == rid:
      r["name"] = name.strip()[:40] or r["name"]
      save_routes(routes, data_dir)
      return True
  return False


def load_trips(data_dir: str = DATA_DIR) -> List[dict]:
  tdir = os.path.join(data_dir, "trips")
  try:
    names = sorted(os.listdir(tdir), reverse=True)
  except OSError:
    return []
  trips = []
  for n in names:
    if n.endswith(".json"):
      d = _read_json(os.path.join(tdir, n), None)
      if d:
        t = TripLog.from_dict(d)
        s = t.summary()
        s["route_id"] = d.get("route_id")
        s["bins"] = t.bins
        trips.append(s)
  return trips


def leaderboards(trips: List[dict], routes: List[dict], top: int = 5) -> List[dict]:
  """Best drive-energy mi/kWh per route (total, events included)."""
  boards = []
  for r in routes:
    runs = [t for t in trips if t.get("route_id") == r["id"] and t["drive_mi_per_kwh"] and t["miles"] >= MIN_SCORED_MILES]
    if runs:
      runs.sort(key=lambda t: t["drive_mi_per_kwh"], reverse=True)
      boards.append({"route": r, "runs": runs[:top], "count": len(runs)})
  return boards


# --- seasons and multi-stop journeys -------------------------------------------

WINTER_MONTHS = {11, 12, 1, 2, 3}
JOURNEY_GAP_S = 30 * 60.0


def season_of(epoch: float) -> str:
  return "Winter" if time.localtime(epoch).tm_mon in WINTER_MONTHS else "Summer"


def season_stats(trips: List[dict], routes: List[dict]) -> List[dict]:
  """Per route and season: runs, average and best driving mi/kWh (events included)."""
  out = []
  for r in routes:
    for season in ("Summer", "Winter"):
      runs = [t for t in trips if t.get("route_id") == r["id"] and t["drive_mi_per_kwh"]
              and t["miles"] >= MIN_SCORED_MILES and season_of(t["start"]) == season]
      if not runs:
        continue
      miles = sum(t["miles"] for t in runs)
      kwh = sum(t["drive_kwh"] for t in runs)
      out.append({"route": r["name"], "season": season, "runs": len(runs),
                  "avg_mi_per_kwh": miles / kwh if kwh > 0.01 else None,
                  "best_mi_per_kwh": max(t["drive_mi_per_kwh"] for t in runs)})
  return out


def journeys(trips: List[dict], route_names: Dict[int, str], gap_s: float = JOURNEY_GAP_S) -> List[dict]:
  """Chain drives with short stops between them (here -> here -> here). Newest first; 2+ legs only."""
  legs = sorted(trips, key=lambda t: t["start"])
  groups: List[List[dict]] = []
  for t in legs:
    if groups and t["start"] - groups[-1][-1]["end"] <= gap_s:
      groups[-1].append(t)
    else:
      groups.append([t])
  out = []
  for g in groups:
    if len(g) < 2:
      continue
    miles = sum(t["miles"] for t in g)
    kwh = sum(t["drive_kwh"] for t in g)
    out.append({
      "start": g[0]["start"], "end": g[-1]["end"], "legs": len(g), "miles": miles, "drive_kwh": kwh,
      "drive_mi_per_kwh": miles / kwh if kwh > 0.01 else None,
      "won_back_kwh": sum(t["won_back_kwh"] for t in g), "lost_kwh": sum(t["lost_kwh"] for t in g),
      "minutes": (g[-1]["end"] - g[0]["start"]) / 60.0,
      "leg_starts": [int(t["start"]) for t in g],
      "leg_names": [route_names.get(t.get("route_id"), f"{t['miles']:.1f} mi") for t in g],
    })
  out.sort(key=lambda j: j["start"], reverse=True)
  return out
