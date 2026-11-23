#!/usr/bin/env python3
"""
smart_ecod - Smart Eco Cruise monitoring daemon (Phase 2/3).

Runs only onroad and only when the "SmartEcoCruise" param is on.
Reads:     carState, carControl, liveLocationKalman, and (optionally) raw CAN
Publishes: smartEcoState
Commands:  NOTHING. This process does not publish sendcan, carControl, or any
           planner message, and nothing in controls/planning subscribes to it.
           Tailgater Mode: the only thing it hands the planner is a larger following time
           (memory param "TailgaterFollowS"), which can only add distance to the car ahead.

Measured HV power (GM 0x2C7 BECMBatteryVoltageCurrent) is read with a private
CANParser in this process, NOT added to carstate's parser. If the message isn't
on the bus, the car's CAN validity is unaffected; this daemon just stops looking
after PROBE_S and falls back to the physics estimate.
"""
import os
import signal
import time

import cereal.messaging as messaging
from cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.frogpilot.functions.smart_eco import EcoInputs, EcoScore, MeasuredPower, SmartEcoMonitor, parse_config
from openpilot.selfdrive.frogpilot.functions import smart_eco_trips as trips
from openpilot.selfdrive.frogpilot.functions import tailgater as tg

RATE_HZ = 20
PARAMS_RELOAD_S = 5.0
PROBE_S = 60.0               # stop draining CAN if the HV message never shows up
HV_MSG = "BECMBatteryVoltageCurrent"
HV_ADDR = 711                # 0x2C7
PT_BUS = 0
CHECKPOINT_S = 30.0
TAILGATER_POLL_S = 0.25
SEGMENT_POLL_S = 2.0


class TailgaterRunner:
  """Glue between the pure TailgaterSession and the device: params, video segments, xattrs."""
  def __init__(self, params, params_memory):
    self.params = params
    self.mem = params_memory
    self.session = tg.TailgaterSession()
    self.night = tg.NightDetector()
    self.requested = False
    self.follow_target = 0.0
    self.segment = None
    self.preserved = set()
    self.last_poll = 0.0
    self.last_seg_poll = -1e9
    self.mem.put_bool("TailgaterMode", False)
    self.mem.put("TailgaterFollowS", "0")

  def current_segment(self, now):
    if now - self.last_seg_poll < SEGMENT_POLL_S:
      return self.segment
    self.last_seg_poll = now
    try:
      from openpilot.system.hardware.hw import Paths
      route = self.params.get("CurrentRoute", encoding="utf8")
      if route:
        segs = [d for d in os.listdir(Paths.log_root()) if d.startswith(route + "--")]
        if segs:
          self.segment = max(segs, key=lambda d: int(d.rpartition("--")[2]))
    except Exception:
      pass
    return self.segment

  def preserve(self, segment):
    if segment in self.preserved:
      return
    try:
      from openpilot.system.hardware.hw import Paths
      os.setxattr(os.path.join(Paths.log_root(), segment), "user.preserve", b"1")
      self.preserved.add(segment)
    except Exception:
      cloudlog.exception("smart_ecod: could not preserve segment")

  def update(self, now, sm, cs, pos):
    if now - self.last_poll >= TAILGATER_POLL_S:
      self.last_poll = now
      self.requested = self.mem.get_bool("TailgaterMode")
      if not self.session.active:  # settings apply from the next session
        self.session.day_follow = min(max(self.params.get_float("TailgaterDayGap") or tg.DAY_FOLLOW_S, 1.5), 5.0)
        self.session.night_follow = min(max(self.params.get_float("TailgaterNightGap") or tg.NIGHT_FOLLOW_S, 1.5), 5.0)
    if sm.updated["wideRoadCameraState"]:
      cam = sm["wideRoadCameraState"]
      scale = 6.0 if cam.sensor == log.FrameData.ImageSensor.ar0231 else 1.0
      self.night.update(max(100.0 - scale * cam.exposureValPercent, 0.0))
    lead = sm["radarState"].leadOne
    segment = self.current_segment(now) if (self.session.active or self.session.incident is not None or self.requested) else None
    target, keep = self.session.update(now, self.requested, sm["controlsState"].enabled, self.night.night, segment,
                                       cs.vEgo, lead.status, lead.dRel, pos)
    if keep != self.requested:
      self.requested = keep
      self.mem.put_bool("TailgaterMode", keep)
    if target != self.follow_target:
      self.follow_target = target
      self.mem.put("TailgaterFollowS", f"{target:.2f}")
    for seg in self.session.segments:
      self.preserve(seg)
    if self.session.ready_to_save(now):
      self.save(now)

  def save(self, now):
    for inc in self.session.pop_finished(now):
      try:
        tg.save_incident(inc)
      except Exception:
        cloudlog.exception("smart_ecod: incident save failed")

  def shutdown(self, now):
    self.session.force_end(now)
    seg = self.current_segment(now + SEGMENT_POLL_S)
    if self.session.incident is not None and seg and seg not in self.session.segments:
      self.session.segments.append(seg)
    for s in self.session.segments:
      self.preserve(s)
    self.save(now)
    try:
      self.mem.put_bool("TailgaterMode", False)
      self.mem.put("TailgaterFollowS", "0")
    except Exception:
      pass


def read_bands(params):
  return [(params.get_float(f"SmartEcoB{i}Min"), params.get_float(f"SmartEcoB{i}Max")) for i in range(1, 6)]


def make_hv_parser(CP):
  if CP.carName != "gm":
    return None
  try:
    from opendbc.can.parser import CANParser
    from openpilot.selfdrive.car.gm.values import DBC
    return CANParser(DBC[CP.carFingerprint]["pt"], [(HV_MSG, 0)], PT_BUS)
  except Exception:
    cloudlog.exception("smart_ecod: HV parser unavailable, using estimate only")
    return None


def main():
  params = Params()
  with car.CarParams.from_bytes(params.get("CarParams", block=True)) as CP:
    car_mass = float(CP.mass)
    hv_parser = make_hv_parser(CP)

  profiles_raw = params.get("SmartEcoProfiles")
  model_raw = params.get("SmartEcoModel")
  bands = read_bands(params)
  cfg = parse_config(profiles_raw, model_raw, bands)
  score = EcoScore(float(cfg.model.get("usable_kwh") or 65.0))

  measured = MeasuredPower(int(cfg.model.get("measured_current_sign") or 0)) if hv_parser else None
  monitor = SmartEcoMonitor(cfg, car_mass, measured)

  can_sock = messaging.sub_sock("can", timeout=0) if hv_parser else None
  sm = messaging.SubMaster(["carState", "carControl", "liveLocationKalman", "controlsState", "radarState", "wideRoadCameraState"],
                           ignore_alive=["controlsState", "radarState", "wideRoadCameraState"],
                           ignore_avg_freq=["controlsState", "radarState", "wideRoadCameraState"],
                           ignore_valid=["controlsState", "radarState", "wideRoadCameraState"])
  pm = messaging.PubMaster(["smartEcoState"])

  start_t = time.monotonic()
  last_reload = start_t
  hv_seen = False
  rk = Ratekeeper(RATE_HZ, print_delay_threshold=None)

  # Trip log: store any drive that ended without a clean shutdown, then start a new one
  try:
    trips.recover_unfinished()
  except Exception:
    cloudlog.exception("smart_ecod: trip recovery failed")
  trip = trips.TripLog(time.time())
  last_checkpoint = start_t
  last_t = start_t

  def _stop(*_):
    raise SystemExit
  signal.signal(signal.SIGTERM, _stop)

  tailgater = TailgaterRunner(params, Params("/dev/shm/params"))

  try:
    _loop(params, monitor, measured, hv_parser, can_sock, sm, pm, rk, trip, car_mass,
          profiles_raw, model_raw, bands, score, start_t, last_reload, hv_seen, last_checkpoint, last_t, tailgater)
  finally:
    try:
      tailgater.shutdown(time.monotonic())
    except Exception:
      cloudlog.exception("smart_ecod: tailgater shutdown failed")
    try:
      trips.finalize(trip)
    except Exception:
      cloudlog.exception("smart_ecod: trip finalize failed")


def _loop(params, monitor, measured, hv_parser, can_sock, sm, pm, rk, trip, car_mass,
          profiles_raw, model_raw, bands, score, start_t, last_reload, hv_seen, last_checkpoint, last_t, tailgater):
  while True:
    sm.update(0)
    now = time.monotonic()

    # Live-reload settings (cheap: params read every few seconds)
    if now - last_reload > PARAMS_RELOAD_S:
      last_reload = now
      p_raw, m_raw, b_now = params.get("SmartEcoProfiles"), params.get("SmartEcoModel"), read_bands(params)
      if p_raw != profiles_raw or m_raw != model_raw or b_now != bands:
        profiles_raw, model_raw, bands = p_raw, m_raw, b_now
        monitor.reconfigure(parse_config(profiles_raw, model_raw, bands), car_mass)

    # Optional measured power
    if can_sock is not None:
      can_strs = messaging.drain_sock_raw(can_sock)
      if can_strs:
        updated = hv_parser.update_strings(can_strs)
        if HV_ADDR in updated:
          hv_seen = True
          vals = hv_parser.vl[HV_MSG]
          measured.update(now, float(vals["HVBatteryVoltage"]), float(vals["HVBatteryCurrent"]))
      if not hv_seen and now - start_t > PROBE_S:
        cloudlog.warning("smart_ecod: 0x2C7 not seen on bus; using power estimate only")
        can_sock = None  # stop paying the CAN-drain cost

    cs = sm["carState"]
    llk = sm["liveLocationKalman"]
    pitch_valid = (sm.valid["liveLocationKalman"] and llk.status == log.LiveLocationKalman.Status.valid
                   and llk.calibratedOrientationNED.valid and len(llk.calibratedOrientationNED.value) == 3)
    inp = EcoInputs(
      t=now,
      v_ego=cs.vEgo,
      a_ego=cs.aEgo,
      pitch=llk.calibratedOrientationNED.value[1] if pitch_valid else 0.0,
      pitch_valid=pitch_valid,
      gas_pressed=cs.gasPressed,
      long_active=sm["carControl"].longActive,
    )
    o = monitor.update(inp)

    # Trip log (route detection uses GPS start/end; stored only on this device)
    pos = None
    if sm.valid["liveLocationKalman"] and llk.positionGeodetic.valid and len(llk.positionGeodetic.value) >= 2:
      pos = (llk.positionGeodetic.value[0], llk.positionGeodetic.value[1])
    dt = min(max(now - last_t, 0.0), 0.5)
    last_t = now
    trip.update(dt, inp.v_ego, inp.a_ego, o.drive_kw, o.target_kw, o.measured_kw, pos,
                bool(cs.leftBlinker or cs.rightBlinker))
    score.update(dt, inp.v_ego, o.drive_kw, o.target_kw)
    try:
      tailgater.update(now, sm, cs, pos)
    except Exception:
      cloudlog.exception("smart_ecod: tailgater update failed")
    trip.eco_score = score.trip_score
    if now - last_checkpoint > CHECKPOINT_S:
      last_checkpoint = now
      try:
        trips.checkpoint(trip)
      except Exception:
        cloudlog.exception("smart_ecod: checkpoint failed")

    msg = messaging.new_message("smartEcoState")
    msg.valid = sm.all_checks(["carState"])
    s = msg.smartEcoState
    s.enabled = True
    s.profileIdx = o.profile_idx
    s.profileMinKw = o.profile_min_kw
    s.profileTargetKw = o.profile_target_kw
    s.targetKw = o.target_kw
    s.vEgo = inp.v_ego
    s.estimatedKw = o.estimated_kw
    s.measuredAvailable = o.measured_kw is not None
    s.measuredKw = o.measured_kw if o.measured_kw is not None else 0.0
    if measured is not None:
      s.measuredSign = measured.sign
      s.hvVoltage = measured.voltage
      s.hvCurrent = measured.current
    s.powerKw = o.power_kw
    s.roadLoadKw = o.road_load_kw
    s.gradePct = o.grade_pct
    s.overTarget = o.over_target
    s.driverOnAccelerator = inp.gas_pressed
    s.driverOverride = o.driver_override
    s.longActive = inp.long_active
    s.recommendedMaxAccel = o.recommended_max_accel
    s.tripEnergyKwh = o.trip_energy_kwh
    s.tripExcessKwh = o.trip_excess_kwh
    s.tripDistanceKm = o.trip_distance_km
    s.tripOverTargetS = o.trip_over_target_s
    s.ecoScore = score.score if score.score is not None else -1.0
    s.ecoTripScore = score.trip_score if score.trip_score is not None else -1.0
    s.paceMiPerKwh = score.pace_mi_per_kwh or 0.0
    s.paceRangeMi = score.pace_range_mi or 0.0
    s.driveKw = o.drive_kw
    s.tailgaterActive = tailgater.session.active
    s.tailgaterFollowS = tailgater.follow_target
    s.tailgaterSecondsLeft = tailgater.session.seconds_left(now)
    pm.send("smartEcoState", msg)

    rk.keep_time()


if __name__ == "__main__":
  main()
