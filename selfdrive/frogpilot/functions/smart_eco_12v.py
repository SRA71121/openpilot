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

Drop test (2 h in all): once the car has been parked DROP_START_S (30 min, when the Bolt goes to
sleep), the voltage is noted, and again DROP_SPAN_S (90 min) later; reported as a per-2-hour rate.
Once a day (first long park with nothing charging) battery12vd holds the comma's shutdown timer
until this finishes; power monitoring caps that hold at 3 h and never overrides low-voltage shutdown. A healthy rested battery barely
moves; a bigger drop points to a weak battery or something draining it. The comma's own draw
during those 2 hours is credited back (COMMA_DRAW_V).

Temperature: the comma's coolest internal sensor at the moment of the reading, minus
SELF_HEAT_C for its own warmth. Taken hours after the car shut off, so defrost, preheat and the
front end can't affect it. Rough: good enough for "below freezing or not", not for a number.

Storage: /data/smart_eco/12v.json
  readings: [[epoch, volts, rest_minutes, short_rest(0/1), temp_c|None, drop_v|None], ...]
            (older 4-field readings are still read; oldest dropped past MAX_READINGS)
  pending:  the latest candidate for the current parking session; saved every few minutes so
            it survives the comma powering off.
"""
import json
import os
from typing import List, Optional

DATA_PATH = "/data/smart_eco/12v.json"
SAMPLE_EVERY_S = 60.0
CHARGING_V = 13.8
REPEAT_WINDOW_S = 14 * 24 * 3600.0   # two low parks within this window = "repeatedly"
DROP_START_S = 30 * 60.0             # first drop-test sample: Bolt asleep, surface charge mostly gone
DROP_SPAN_S = 1.5 * 3600.0           # second sample this long after the first (whole test = 2 h)
DROP_RATE_S = 2 * 3600.0             # drops are reported per 2 hours so the warning setting keeps its meaning
COMMA_DRAW_V = 0.01                  # comma draw over 2 h (~1 Ah), credited back to the battery
DAILY_TEST_GAP_S = 20 * 3600.0       # stay-on test at most once per ~day
HOLD_S = DROP_START_S + DROP_SPAN_S + 120.0
SELF_HEAT_C = 8.0                    # comma idles this much warmer than the cabin (rough)
COLD_C = 0.0                         # 32 F
RISE_V = 0.05                        # a resting battery never climbs on its own: a rise this big ...
RISE_HOLD_S = 10.0                   # ... held this long means something charged it (DC-DC top-off, charger)
HISTORY_PATH = "/data/smart_eco/12v_batteries.json"

STATUS_OK, STATUS_LOW, STATUS_REPEAT, STATUS_COLD = 0, 1, 2, 3
SHORT_REST_S = 30 * 60.0
MAX_READINGS = 400


class Battery12VLog:
  def __init__(self, readings: Optional[List[list]] = None, pending: Optional[dict] = None,
               last_test_t: float = 0.0, skip_until_t: float = 0.0):
    self.readings: List[list] = readings or []
    self.pending: Optional[dict] = pending      # {"t", "v", "park_t"}
    self._driving: Optional[bool] = None
    self._park_t: Optional[float] = pending.get("park_t") if pending else None
    self._last_sample_t = float("-inf")
    self._parked_at: Optional[float] = None
    self._rest_min_v: Optional[float] = None
    self._rise_since: Optional[float] = None
    self.restarts = 0
    self.installed_t = 0.0          # readings before the current battery's install don't count
    self.last_test_t = float(last_test_t or 0.0)    # when the last full stay-on test finished
    self.skip_until_t = float(skip_until_t or 0.0)  # charging cancelled today's test until then

  # --- recording ---------------------------------------------------------------
  def add(self, t: float, volts: float, driving: bool, temp_c: Optional[float] = None) -> bool:
    """Feed every reading. Returns True when the parking candidate was updated."""
    if driving:
      if not self._driving:
        self.commit()            # drive started: last parked reading becomes the session's reading
      self._driving = True
      self._park_t = None
      return False

    if self._driving or self._driving is None:
      self._parked_at = t
    if self._driving:
      self._park_t = t           # just parked
      self._rest_min_v = None
      self._rise_since = None
    self._driving = False
    if volts < 5.0 or volts > 20.0:
      return False               # no reading
    if volts >= CHARGING_V:
      self._restart(t)           # DC-DC running (charging): rest clock restarts when it stops
      return False
    # Brief top-offs can sit below CHARGING_V or fall between samples: any sustained climb
    # above the lowest voltage seen this rest means something fed the battery.
    if self._rest_min_v is None or volts < self._rest_min_v:
      self._rest_min_v = volts
      self._rise_since = None
    elif volts > self._rest_min_v + RISE_V:
      if self._rise_since is None:
        self._rise_since = t
      elif t - self._rise_since >= RISE_HOLD_S:
        self._restart(t)
        self._rest_min_v = volts
        return False
    else:
      self._rise_since = None
    if t - self._last_sample_t < SAMPLE_EVERY_S:
      return False
    self._last_sample_t = t
    prev = self.pending if (self.pending and self.pending.get("park_t") == self._park_t) else {}
    self.pending = {"t": round(t, 1), "v": round(volts, 3), "park_t": self._park_t,
                    "temp": round(temp_c, 1) if temp_c is not None else None,
                    "d0": prev.get("d0"), "d1": prev.get("d1")}
    if self._park_t is not None:
      rest = t - self._park_t
      if self.pending["d0"] is None and rest >= DROP_START_S:
        self.pending["d0"] = [round(t, 1), round(volts, 3)]
      d0 = self.pending["d0"]
      if d0 is not None and self.pending["d1"] is None and t - d0[0] >= DROP_SPAN_S:
        self.pending["d1"] = [round(t, 1), round(volts, 3)]
    return True

  def _restart(self, t: float):
    # Something fed the battery (plugged in, DC-DC top-off): today's stay-on test is off.
    # Ignore the DC-DC still winding down in the first couple of minutes after parking.
    parked_for = t - self._parked_at if self._parked_at is not None else 0.0
    if self._park_t is not None and not self._driving and parked_for > 120.0 and self.hold_wanted(t):
      self.skip_until_t = t + DAILY_TEST_GAP_S
    self._park_t = t
    self.pending = None
    self._rest_min_v = None
    self._rise_since = None
    self.restarts += 1

  def hold_wanted(self, t: float) -> bool:
    """Should the comma stay on past its shutdown timer to finish today's battery test?
    Only while parked, once per day, not after charging cancelled it, and only until the test is done."""
    if self._driving or self._park_t is None:
      return False
    if (self.last_test_t and t - self.last_test_t < DAILY_TEST_GAP_S) or t < self.skip_until_t:
      return False
    if self.pending and self.pending.get("d1"):
      return False
    return t - self._park_t < HOLD_S

  def note_test_done(self, t: float):
    if self.pending and self.pending.get("d1") and (not self.last_test_t or t - self.last_test_t >= DAILY_TEST_GAP_S):
      self.last_test_t = t

  def commit(self):
    """Turn the pending candidate into the session's reading (on drive start)."""
    p, self.pending = self.pending, None
    if not p:
      return
    rest_s = (p["t"] - p["park_t"]) if p.get("park_t") is not None else None
    short = 1 if (rest_s is None or rest_s < SHORT_REST_S) else 0
    rest_min = round(rest_s / 60.0, 1) if rest_s is not None else -1
    drop = None
    if p.get("d0") and p.get("d1"):
      span = max(p["d1"][0] - p["d0"][0], 1.0)
      drop = round(max(0.0, (p["d0"][1] - p["d1"][1]) * DROP_RATE_S / span - COMMA_DRAW_V), 3)
    self.readings.append([p["t"], p["v"], rest_min, short, p.get("temp"), drop])
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
  def status(self, warn_v: float) -> int:
    """OK while the latest trusted reading is at/above the warning (charged or replaced).
    REPEAT when it's below and another trusted low reading happened within REPEAT_WINDOW_S
    before it, even with a good (charged) reading in between. Otherwise COLD when it's below and
    the reading was taken below freezing, or LOW."""
    t = [r for r in self.trusted() if r[0] >= self.installed_t]
    if not t or t[-1][1] >= warn_v:
      return STATUS_OK
    latest_t = t[-1][0]
    earlier_lows = [r for r in t[:-1] if r[1] < warn_v and latest_t - r[0] <= REPEAT_WINDOW_S]
    if earlier_lows:
      return STATUS_REPEAT
    return STATUS_COLD if self.was_cold(t[-1]) else STATUS_LOW

  @staticmethod
  def was_cold(reading: list) -> bool:
    temp = reading[4] if len(reading) > 4 else None
    return temp is not None and temp - SELF_HEAT_C < COLD_C

  def drop(self, limit_v: float) -> Optional[float]:
    """The latest parking session's 2-hour drop if it's over the limit (None otherwise or untested)."""
    if not self.readings or self.readings[-1][0] < self.installed_t:
      return None
    r = self.readings[-1]
    d = r[5] if len(r) > 5 else None
    return d if (d is not None and d > limit_v) else None

  def to_dict(self) -> dict:
    return {"readings": self.readings, "pending": self.pending,
            "last_test_t": self.last_test_t, "skip_until_t": self.skip_until_t}

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
      return cls(d.get("readings") or [], d.get("pending"), d.get("last_test_t") or 0.0, d.get("skip_until_t") or 0.0)
    except (OSError, ValueError, AttributeError, TypeError):
      return cls()


# ---- battery history -------------------------------------------------------------------------
# [{"installed": epoch, "type": "Lead-acid"|"AGM"|"LiFePO4"|..., "note": str}, ...] oldest first.
# A battery's service ends when the next one is installed.

def load_history(path: str = HISTORY_PATH) -> List[dict]:
  try:
    with open(path) as f:
      h = json.load(f)
    return sorted([b for b in h if isinstance(b, dict) and "installed" in b], key=lambda b: b["installed"])
  except Exception:
    return []


def save_history(history: List[dict], path: str = HISTORY_PATH) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(sorted(history, key=lambda b: b["installed"]), f)
  os.replace(tmp, path)


def add_install(installed: float, btype: str = "", note: str = "", path: str = HISTORY_PATH) -> List[dict]:
  h = [b for b in load_history(path) if abs(b["installed"] - installed) > 3600]  # same day re-entry replaces
  h.append({"installed": float(installed), "type": btype[:20], "note": note[:80]})
  save_history(h, path)
  return load_history(path)


def current_install_t(path: str = HISTORY_PATH) -> float:
  h = load_history(path)
  return h[-1]["installed"] if h else 0.0


def battery_summaries(history: List[dict], readings: List[list], warn_v: float, drain_v: float, now: float) -> List[dict]:
  """One row per battery, newest first: days in service, parks tested, rested voltage, warnings."""
  out = []
  for i, b in enumerate(history):
    start = b["installed"]
    end = history[i + 1]["installed"] if i + 1 < len(history) else None
    rs = [r for r in readings if r[0] >= start and (end is None or r[0] < end)]
    rested = [r for r in rs if not r[3]]
    recent = [r[1] for r in rested if r[0] >= (end or now) - 30 * 86400]
    drops = [r[5] for r in rs if len(r) > 5 and r[5] is not None]
    out.append({
      "installed": start, "removed": end, "type": b.get("type", ""), "note": b.get("note", ""),
      "days": round(((end or now) - start) / 86400.0, 1), "current": end is None,
      "parks": len(rested), "drop_tests": len(drops),
      "avg_30d": round(sum(recent) / len(recent), 2) if recent else None,
      "lowest": round(min(r[1] for r in rested), 2) if rested else None,
      "low_count": sum(1 for r in rested if r[1] < warn_v),
      "drain_count": sum(1 for d in drops if d > drain_v),
      "worst_drop": round(max(drops), 2) if drops else None,
    })
  return list(reversed(out))
