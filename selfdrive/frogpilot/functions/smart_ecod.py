#!/usr/bin/env python3
"""
smart_ecod - Smart Eco Cruise monitoring daemon (Phase 2/3).

Runs only onroad and only when the "SmartEcoCruise" param is on.
Reads:     carState, carControl, liveLocationKalman, and (optionally) raw CAN
Publishes: smartEcoState
Commands:  NOTHING. This process does not publish sendcan, carControl, or any
           planner message, and nothing in controls/planning subscribes to it.

Measured HV power (GM 0x2C7 BECMBatteryVoltageCurrent) is read with a private
CANParser in this process, NOT added to carstate's parser. If the message isn't
on the bus, the car's CAN validity is unaffected; this daemon just stops looking
after PROBE_S and falls back to the physics estimate.
"""
import signal
import time

import cereal.messaging as messaging
from cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.frogpilot.functions.smart_eco import EcoInputs, MeasuredPower, SmartEcoMonitor, parse_config
from openpilot.selfdrive.frogpilot.functions import smart_eco_trips as trips

RATE_HZ = 20
PARAMS_RELOAD_S = 5.0
PROBE_S = 60.0               # stop draining CAN if the HV message never shows up
HV_MSG = "BECMBatteryVoltageCurrent"
HV_ADDR = 711                # 0x2C7
PT_BUS = 0
CHECKPOINT_S = 30.0


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
  cfg = parse_config(profiles_raw, model_raw)

  measured = MeasuredPower(int(cfg.model.get("measured_current_sign") or 0)) if hv_parser else None
  monitor = SmartEcoMonitor(cfg, car_mass, measured)

  can_sock = messaging.sub_sock("can", timeout=0) if hv_parser else None
  sm = messaging.SubMaster(["carState", "carControl", "liveLocationKalman"])
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

  try:
    _loop(params, monitor, measured, hv_parser, can_sock, sm, pm, rk, trip, car_mass,
          profiles_raw, model_raw, start_t, last_reload, hv_seen, last_checkpoint, last_t)
  finally:
    try:
      trips.finalize(trip)
    except Exception:
      cloudlog.exception("smart_ecod: trip finalize failed")


def _loop(params, monitor, measured, hv_parser, can_sock, sm, pm, rk, trip, car_mass,
          profiles_raw, model_raw, start_t, last_reload, hv_seen, last_checkpoint, last_t):
  while True:
    sm.update(0)
    now = time.monotonic()

    # Live-reload settings (cheap: params read every few seconds)
    if now - last_reload > PARAMS_RELOAD_S:
      last_reload = now
      p_raw, m_raw = params.get("SmartEcoProfiles"), params.get("SmartEcoModel")
      if p_raw != profiles_raw or m_raw != model_raw:
        profiles_raw, model_raw = p_raw, m_raw
        monitor.reconfigure(parse_config(profiles_raw, model_raw), car_mass)

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
                   and llk.orientationNED.valid and len(llk.orientationNED.value) == 3)
    inp = EcoInputs(
      t=now,
      v_ego=cs.vEgo,
      a_ego=cs.aEgo,
      pitch=llk.orientationNED.value[1] if pitch_valid else 0.0,
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
    trip.update(dt, inp.v_ego, inp.a_ego, o.drive_kw, o.measured_kw, o.power_kw - o.target_kw, o.over_target, pos)
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
    pm.send("smartEcoState", msg)

    rk.keep_time()


if __name__ == "__main__":
  main()
