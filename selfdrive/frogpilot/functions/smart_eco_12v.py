"""
Smart Eco - 12V battery monitor (pure logic + storage, no openpilot imports).

Samples the car's 12V as seen by the comma (peripheralState.voltage). While driving the
Bolt's DC-DC holds it near 14 V, so the interesting numbers are while PARKED:
  resting   = parked and at least REST_AFTER_S since the last drive (surface charge gone)
  pre-drive = the last resting reading before a drive starts (best daily health number)
Stored in /data/smart_eco/12v.json (about two weeks of samples).
"""
import json
import os
from typing import List, Optional

DATA_PATH = "/data/smart_eco/12v.json"
KEEP_S = 14 * 86400
ONROAD_EVERY_S = 60.0
OFFROAD_EVERY_S = 300.0
REST_AFTER_S = 30 * 60.0
MAX_SAMPLES = 6000


class Battery12VLog:
  def __init__(self, samples: Optional[List[list]] = None, last_drive_end: float = 0.0):
    # samples: [epoch, volts, driving(0/1)]
    self.samples: List[list] = samples or []
    self.last_drive_end = last_drive_end
    self._last_sample_t = self.samples[-1][0] if self.samples else float("-inf")
    self._driving = False

  # --- recording ---------------------------------------------------------------
  def add(self, t: float, volts: float, driving: bool) -> bool:
    """Feed every reading; stores at the right cadence. Returns True when it stored one."""
    if volts < 5.0 or volts > 20.0:   # nonsense / no panda
      return False
    ended_now = self._driving and not driving
    if ended_now:
      self.last_drive_end = t
    started_now = driving and not self._driving
    self._driving = driving
    every = ONROAD_EVERY_S if driving else OFFROAD_EVERY_S
    if not (started_now or ended_now) and t - self._last_sample_t < every:
      return False
    # the sample at the moment a drive ends is tagged as driving: it marks the drive's end
    self.samples.append([round(t, 1), round(volts, 3), 1 if (driving or ended_now) else 0])
    self._last_sample_t = t
    cutoff = t - KEEP_S
    while self.samples and (self.samples[0][0] < cutoff or len(self.samples) > MAX_SAMPLES):
      self.samples.pop(0)
    return True

  # --- analysis ----------------------------------------------------------------
  def resting(self) -> List[list]:
    """Parked samples taken long enough after a drive to reflect true resting voltage."""
    out, last_drive = [], None
    for t, v, d in self.samples:
      if d:
        last_drive = t
      elif last_drive is None or t - last_drive >= REST_AFTER_S:
        out.append([t, v])
    return out

  def latest_resting(self) -> Optional[float]:
    r = self.resting()
    return r[-1][1] if r else None

  def pre_drive(self) -> List[list]:
    """Last resting reading before each drive started: [drive_start_epoch, volts]."""
    out, last_rest, prev_d = [], None, 0
    rest_ts = {t for t, _ in self.resting()}
    for t, v, d in self.samples:
      if not d and t in rest_ts:
        last_rest = v
      if d and not prev_d and last_rest is not None:
        out.append([t, last_rest])
        last_rest = None
      prev_d = d
    return out

  def low(self, warn_v: float) -> Optional[float]:
    v = self.latest_resting()
    return v if (v is not None and v < warn_v) else None

  # --- storage -----------------------------------------------------------------
  def to_dict(self) -> dict:
    return {"samples": self.samples, "last_drive_end": self.last_drive_end}

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
      return cls(d.get("samples", []), d.get("last_drive_end", 0.0))
    except (OSError, ValueError, AttributeError):
      return cls()
