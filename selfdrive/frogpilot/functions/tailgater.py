"""Tailgater Mode (Smart Eco fork).

The driver turns it on with a tap. While it's on:
  * openpilot (only when it is already controlling speed) keeps a bigger gap to the car ahead:
    DAY_FOLLOW_S, or NIGHT_FOLLOW_S when it's dark. The gap opens gradually (FOLLOW_RAMP per second)
    so the car eases off instead of braking in front of the tailgater. Braking ability is never limited.
  * Power Ceiling and Highway Glide pause.
  * Video is locked from the minute before the tap until AFTER_S after it ends, and an incident
    record is written for Fleet Manager.
It ends on a second tap, after MAX_S, when openpilot disengages (if it was engaged), or when the car
is turned off. The driver keeps full control the whole time: gas, brake and steering override as usual.
"""
import json
import os
import time

DAY_FOLLOW_S = 2.5
NIGHT_FOLLOW_S = 3.0
FOLLOW_RAMP = 0.1        # s of following time added per second while opening the gap
FOLLOW_RELEASE = 0.2     # s per second when handing back to the normal gap
MAX_S = 600.0
AFTER_S = 60.0
NIGHT_LIGHT = 30.0       # same 0-100 scale as the screen's light sensor; below this counts as night
DAY_LIGHT = 40.0         # hysteresis back to day

INCIDENT_DIR = "/data/smart_eco"
INCIDENT_FILE = "incidents.json"
INCIDENT_MAX = 100


def ramp_follow(current: float, base: float, target: float, dt: float) -> float:
  """Follow time to use this step. target <= 0 means hand back to base."""
  current = max(current, base) if current > 0 else base
  if target > 0:
    goal = max(target, base)
    return min(goal, current + FOLLOW_RAMP * dt) if current < goal else goal
  return max(base, current - FOLLOW_RELEASE * dt)


class NightDetector:
  def __init__(self):
    self.night = False

  def update(self, light: float) -> bool:
    if self.night and light > DAY_LIGHT:
      self.night = False
    elif not self.night and light < NIGHT_LIGHT:
      self.night = True
    return self.night


class TailgaterSession:
  def __init__(self):
    self.day_follow = DAY_FOLLOW_S
    self.night_follow = NIGHT_FOLLOW_S
    self.active = False
    self.started_at = 0.0
    self.ended_at = 0.0
    self.recording_until = 0.0
    self.was_engaged = False
    self.segments: list[str] = []
    self.incident: dict | None = None
    self.completed: list[dict] = []  # finished incidents waiting to be written

  # ---- state ---------------------------------------------------------------------------------
  def update(self, now: float, requested: bool, engaged: bool, night: bool, segment: str | None,
             v_ego: float = 0.0, lead_status: bool = False, d_rel: float = 0.0, pos=None, wall=None):
    """Returns (follow_target_s, request_should_be) where follow_target_s is 0 when inactive."""
    wall = time.time() if wall is None else wall
    keep_request = requested

    if requested and not self.active:
      if self.incident is not None:  # tapped again during the minute-after window: close out the last one
        self.completed.append(self.take_incident())
      self._start(now, wall, engaged, night, pos)
    elif self.active:
      self.was_engaged |= engaged
      reason = ""
      if not requested:
        reason = "tapped off"
      elif now - self.started_at >= MAX_S:
        reason = "time limit"
      elif self.was_engaged and not engaged:
        reason = "disengaged"
      if reason:
        self._end(now, wall, reason)
        keep_request = False

    if self.active:
      self._stats(v_ego, lead_status, d_rel, night)

    recording = self.active or (self.incident is not None and now < self.recording_until)
    if recording and segment and segment not in self.segments:
      self.segments.append(segment)

    target = (self.night_follow if night else self.day_follow) if self.active else 0.0
    return target, keep_request

  def seconds_left(self, now: float) -> float:
    return max(0.0, MAX_S - (now - self.started_at)) if self.active else 0.0

  def ready_to_save(self, now: float) -> bool:
    return bool(self.completed) or (self.incident is not None and not self.active and now >= self.recording_until)

  def pop_finished(self, now: float) -> list[dict]:
    out, self.completed = self.completed, []
    if self.incident is not None and not self.active and now >= self.recording_until:
      out.append(self.take_incident())
    return out

  def take_incident(self) -> dict | None:
    inc, self.incident = self.incident, None
    if inc is not None:
      inc["segments"] = list(self.segments)
      self.segments = []
    return inc

  def force_end(self, now: float, wall=None):
    """Car turned off / process stopping."""
    if self.active:
      self._end(now, time.time() if wall is None else wall, "car off")
    self.recording_until = now

  # ---- internals ---------------------------------------------------------------------------
  def _start(self, now, wall, engaged, night, pos):
    self.active = True
    self.started_at = now
    self.was_engaged = engaged
    self.segments = []
    self.incident = {"start": int(wall), "end": None, "seconds": 0, "night": night, "engaged": engaged,
                     "start_pos": list(pos) if pos else None, "max_mph": 0.0, "min_gap_s": None,
                     "end_reason": ""}

  def _end(self, now, wall, reason):
    self.active = False
    self.ended_at = now
    self.recording_until = now + AFTER_S
    if self.incident is not None:
      self.incident["end"] = int(wall)
      self.incident["seconds"] = int(round(now - self.started_at))
      self.incident["end_reason"] = reason

  def _stats(self, v_ego, lead_status, d_rel, night):
    inc = self.incident
    if inc is None:
      return
    inc["max_mph"] = round(max(inc["max_mph"], v_ego / 0.44704), 1)
    inc["night"] = inc["night"] or night
    if lead_status and v_ego > 1.0 and d_rel > 0:
      gap = d_rel / v_ego
      inc["min_gap_s"] = round(gap if inc["min_gap_s"] is None else min(inc["min_gap_s"], gap), 2)


# ---- storage ---------------------------------------------------------------------------------
def save_incident(inc: dict, data_dir: str = INCIDENT_DIR) -> None:
  os.makedirs(data_dir, exist_ok=True)
  items = load_incidents(data_dir)
  items.append(inc)
  items = items[-INCIDENT_MAX:]
  tmp = os.path.join(data_dir, INCIDENT_FILE + ".tmp")
  with open(tmp, "w") as f:
    json.dump(items, f)
  os.replace(tmp, os.path.join(data_dir, INCIDENT_FILE))


def load_incidents(data_dir: str = INCIDENT_DIR) -> list:
  try:
    with open(os.path.join(data_dir, INCIDENT_FILE)) as f:
      items = json.load(f)
    return items if isinstance(items, list) else []
  except Exception:
    return []


def incident_links(segments: list[str]) -> list[dict]:
  """Links for the minute before the first locked segment plus every locked segment."""
  links = [segment_links(s) for s in segments]
  if links and links[0]["seg"].isdigit() and int(links[0]["seg"]) > 0:
    links.insert(0, {"route": links[0]["route"], "seg": str(int(links[0]["seg"]) - 1)})
  return links


def segment_links(segment: str) -> dict:
  """'2026-11-23--13-40-02--5' -> route and query used by Fleet Manager's /footage/<route>?<seg>,<camera>."""
  route, _, seg = segment.rpartition("--")
  return {"route": route, "seg": seg}
