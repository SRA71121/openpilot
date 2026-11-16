"""
Smart Eco - 12V battery health (pure logic + storage, no openpilot imports).

One reading per parking session, taken as late as possible: the last parked sample before
the comma shuts itself off (or before the next drive starts, if it never shut down). With a
6-hour shutdown timer that's a reading after ~6 hours of rest.

Rules
  - Nothing is sampled while driving (that's just the DC-DC converter's output).
  - Samples at or above CHARGING_V look like the DC-DC is running (car on or plugged in and
    charging) and are skipped, and the rest clock restarts once charging stops, so a charger
    can't make the battery look healthier than it is.
  - A reading taken less than SHORT_REST_S after parking still has surface charge on it and is
    flagged as "short rest" (shown, but not used for the warning).

Storage: /data/smart_eco/12v.json
  readings: [[epoch, volts, rest_minutes, short_rest(0/1)], ...]   (oldest dropped past MAX_READINGS)
  pending:  the latest candidate for the current parking session; saved every few minutes so
            it survives the comma powering off.
"""
import json
import os
from typing import List, Optional

DATA_PATH = "/data/smart_eco/12v.json"
SAMPLE_EVERY_S = 60.0
CHARGING_V = 13.8
SHORT_REST_S = 30 * 60.0
MAX_READINGS = 400


class Battery12VLog:
  def __init__(self, readings: Optional[List[list]] = None, pending: Optional[dict] = None):
    self.readings: List[list] = readings or []
    self.pending: Optional[dict] = pending      # {"t", "v", "park_t"}
    self._driving: Optional[bool] = None
    self._park_t: Optional[float] = pending.get("park_t") if pending else None
    self._last_sample_t = float("-inf")

  # --- recording ---------------------------------------------------------------
  def add(self, t: float, volts: float, driving: bool) -> bool:
    """Feed every reading. Returns True when the parking candidate was updated."""
    if driving:
      if not self._driving:
        self.commit()            # drive started: last parked reading becomes the session's reading
      self._driving = True
      self._park_t = None
      return False

    if self._driving:
      self._park_t = t           # just parked
    self._driving = False
    if volts < 5.0 or volts > 20.0:
      return False               # no reading
    if volts >= CHARGING_V:
      self._park_t = t           # DC-DC running (charging): rest clock restarts when it stops
      self.pending = None
      return False
    if t - self._last_sample_t < SAMPLE_EVERY_S:
      return False
    self._last_sample_t = t
    self.pending = {"t": round(t, 1), "v": round(volts, 3), "park_t": self._park_t}
    return True

  def commit(self):
    """Turn the pending candidate into the session's reading (on drive start)."""
    p, self.pending = self.pending, None
    if not p:
      return
    rest_s = (p["t"] - p["park_t"]) if p.get("park_t") is not None else None
    short = 1 if (rest_s is None or rest_s < SHORT_REST_S) else 0
    rest_min = round(rest_s / 60.0, 1) if rest_s is not None else -1
    self.readings.append([p["t"], p["v"], rest_min, short])
    if len(self.readings) > MAX_READINGS:
      self.readings = self.readings[-MAX_READINGS:]

  # --- analysis ----------------------------------------------------------------
  def trusted(self) -> List[list]:
    return [r for r in self.readings if not r[3]]

  def latest(self) -> Optional[list]:
    """Most recent trusted reading [epoch, volts, rest_min, 0]."""
    t = self.trusted()
    return t[-1] if t else None

  def low(self, warn_v: float) -> Optional[float]:
    r = self.latest()
    return r[1] if (r is not None and r[1] < warn_v) else None

  # --- storage -----------------------------------------------------------------
  def to_dict(self) -> dict:
    return {"readings": self.readings, "pending": self.pending}

  def save(self, path: str = DATA_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
      json.dump(self.to_dict(), f)
    os.replace(tmp, path)

  @classmethod
  def load(cls, path: str = DATA_PATH) -> "Battery12VLog":
    try:
      with open(path) as f:
        d = json.load(f)
      return cls(d.get("readings") or [], d.get("pending"))
    except (OSError, ValueError, AttributeError, TypeError):
      return cls()
