"""
Smart Eco Cruise - trip log, route leaderboards and speed-vs-power stats.

Pure Python (no openpilot imports) so it runs off-device in tests and inside the
Fleet Manager web page. Data lives in /data/smart_eco/ on the comma:
  trips/<start_epoch>.json   one file per finished drive
  current.json               checkpoint of the drive in progress
  routes.json                auto-detected repeat routes (start/end clusters) and their names

Energy terms
  drive_kwh     propulsion energy from the physics model (net of regen); used for rankings
  measured_kwh  real pack energy (V x I) when the car broadcasts it; includes heat/accessories
  accessory_kwh measured_kwh - drive_kwh (heater, defrost, 12V...). Only when measured exists.
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


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
  lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
  h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371000.0 * math.asin(math.sqrt(h))


class TripLog:
  def __init__(self, start_epoch: Optional[float] = None):
    self.start_epoch = start_epoch if start_epoch is not None else time.time()
    self.end_epoch = self.start_epoch
    self.dist_m = 0.0
    self.time_s = 0.0
    self.moving_s = 0.0
    self.drive_kwh = 0.0
    self.measured_kwh = 0.0
    self.measured_drive_kwh = 0.0   # model drive energy over the same samples as measured (for accessory split)
    self.measured_s = 0.0
    self.excess_kwh = 0.0
    self.over_target_s = 0.0
    self.start_pos: Optional[List[float]] = None
    self.end_pos: Optional[List[float]] = None
    # bins: str(bin_index) -> [time_s, drive_kwh, steady_s, steady_drive_kwh, steady_measured_s, steady_measured_kwh]
    self.bins: Dict[str, List[float]] = {}

  def update(self, dt: float, v: float, a: float, drive_kw: float, measured_kw: Optional[float],
             excess_kw: float, over_target: bool, pos: Optional[Tuple[float, float]] = None):
    if dt <= 0:
      return
    self.end_epoch = self.start_epoch + self.time_s + dt
    self.time_s += dt
    self.dist_m += max(v, 0.0) * dt
    self.drive_kwh += drive_kw * dt / 3600.0
    self.excess_kwh += max(excess_kw, 0.0) * dt / 3600.0
    if over_target:
      self.over_target_s += dt
    if measured_kw is not None:
      self.measured_kwh += measured_kw * dt / 3600.0
      self.measured_drive_kwh += drive_kw * dt / 3600.0
      self.measured_s += dt
    if pos is not None:
      if self.start_pos is None:
        self.start_pos = [pos[0], pos[1]]
      self.end_pos = [pos[0], pos[1]]

    if v > 0.5:
      self.moving_s += dt
      b = self.bins.setdefault(str(int(v * MPH // BIN_MPH)), [0.0] * 6)
      b[0] += dt
      b[1] += drive_kw * dt / 3600.0
      if abs(a) < STEADY_ACCEL:
        b[2] += dt
        b[3] += drive_kw * dt / 3600.0
        if measured_kw is not None:
          b[4] += dt
          b[5] += measured_kw * dt / 3600.0

  # --- derived numbers ------------------------------------------------------
  @property
  def miles(self) -> float:
    return self.dist_m * MI_PER_M

  def summary(self) -> dict:
    mi = self.miles
    acc = (self.measured_kwh - self.measured_drive_kwh) if self.measured_s > 0 else None
    return {
      "start": self.start_epoch, "end": self.end_epoch, "miles": mi,
      "minutes": self.time_s / 60.0,
      "avg_mph": (mi / (self.moving_s / 3600.0)) if self.moving_s > 1 else 0.0,
      "drive_kwh": self.drive_kwh,
      "drive_mi_per_kwh": (mi / self.drive_kwh) if self.drive_kwh > 0.01 else None,
      "measured_kwh": self.measured_kwh if self.measured_s > 0 else None,
      "measured_coverage": self.measured_s / self.time_s if self.time_s > 0 else 0.0,
      "accessory_kwh": acc,
      "excess_kwh": self.excess_kwh,
      "over_target_min": self.over_target_s / 60.0,
    }

  def to_dict(self) -> dict:
    return {k: getattr(self, k) for k in ("start_epoch", "end_epoch", "dist_m", "time_s", "moving_s", "drive_kwh",
                                           "measured_kwh", "measured_drive_kwh", "measured_s", "excess_kwh",
                                           "over_target_s", "start_pos", "end_pos", "bins")}

  @classmethod
  def from_dict(cls, d: dict) -> "TripLog":
    t = cls(d.get("start_epoch", 0.0))
    for k, v in d.items():
      if hasattr(t, k):
        setattr(t, k, v)
    return t


def speed_table(bins_list: List[Dict[str, List[float]]]) -> List[dict]:
  """Combine bins from one or more trips into rows for the proof table."""
  merged: Dict[int, List[float]] = {}
  for bins in bins_list:
    for k, b in bins.items():
      m = merged.setdefault(int(k), [0.0] * 6)
      for i in range(6):
        m[i] += b[i]
  rows = []
  for idx in sorted(merged):
    t, e, st, se, sms, sme = merged[idx]
    rows.append({
      "range": f"{idx * BIN_MPH}-{(idx + 1) * BIN_MPH}",
      "minutes": t / 60.0,
      "avg_kw": e * 3600.0 / t if t > 0 else 0.0,
      "steady_minutes": st / 60.0,
      "steady_kw": se * 3600.0 / st if st > 0 else None,
      "steady_measured_kw": sme * 3600.0 / sms if sms > 0 else None,
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
  """Best drive-energy mi/kWh per route. Heat is shown beside, never counted."""
  boards = []
  for r in routes:
    runs = [t for t in trips if t.get("route_id") == r["id"] and t["drive_mi_per_kwh"] and t["miles"] >= MIN_SCORED_MILES]
    if runs:
      runs.sort(key=lambda t: t["drive_mi_per_kwh"], reverse=True)
      boards.append({"route": r, "runs": runs[:top], "count": len(runs)})
  return boards
