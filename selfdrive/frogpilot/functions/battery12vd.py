#!/usr/bin/env python3
"""
battery12vd - Smart Eco 12V battery health.

Runs whenever the comma is on and Smart Eco is enabled. While parked it keeps the latest
12V reading as the parking session's candidate (saved every few minutes so it survives the
comma shutting itself off); when the next drive starts, that last reading is recorded.
Your Device Shutdown Timer therefore sets how long the battery has rested.
Reads only peripheralState and deviceState. Commands nothing.
Shows an offroad alert when the latest trusted reading is below "SmartEco12VWarn".
"""
import signal
import time

import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.alertmanager import set_offroad_alert
from openpilot.selfdrive.frogpilot.functions.smart_eco_12v import Battery12VLog, STATUS_LOW, STATUS_REPEAT, STATUS_COLD, \
                                                                 add_install, current_install_t

ALERT = "Offroad_SmartEco12VLow"
ALERT_REPEAT = "Offroad_SmartEco12VRepeat"
ALERT_COLD = "Offroad_SmartEco12VCold"
ALERT_DRAIN = "Offroad_SmartEco12VDrain"
STATUS_PARAM = "SmartEco12VStatus"   # read by controlsd for the banner at car start: low status + 10 if draining


def device_temp_c(ds):
  """Coolest of the comma's internal sensors (closest to the cabin), None if nothing usable."""
  vals = []
  try:
    vals += [float(ds.memoryTempC)]
    vals += [float(x) for x in ds.pmicTempC]
    vals += [float(x) for x in ds.cpuTempC]
  except Exception:
    pass
  vals = [v for v in vals if -40.0 < v < 120.0 and v != 0.0]
  return min(vals) if vals else None
SAVE_EVERY_S = 300.0


def main():
  params = Params()
  log12 = Battery12VLog.load()
  sm = messaging.SubMaster(["peripheralState", "deviceState"])
  rk = Ratekeeper(1.0, print_delay_threshold=None)
  last_save = time.monotonic()
  status = None
  log12.installed_t = current_install_t()
  params_memory = Params("/dev/shm/params")
  hold = False
  params_memory.put_bool("SmartEco12VHold", False)

  def _stop(*_):
    raise SystemExit
  signal.signal(signal.SIGTERM, _stop)

  try:
    while True:
      sm.update(0)
      now = time.monotonic()
      # New battery recorded from the comma's settings
      req = params.get("SmartEco12VInstallRequest", encoding="utf8")
      if req:
        params.remove("SmartEco12VInstallRequest")
        try:
          parts = req.split("|")
          add_install(float(parts[0]), parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else "")
          log12.installed_t = current_install_t()
          status = None   # re-evaluate warnings for the new battery
        except Exception:
          cloudlog.exception("battery12vd: install record failed")

      if sm.seen["peripheralState"]:
        volts = sm["peripheralState"].voltage / 1000.0
        driving = bool(sm["deviceState"].started) if sm.seen["deviceState"] else False
        temp_c = device_temp_c(sm["deviceState"]) if sm.seen["deviceState"] else None
        n_before = len(log12.readings)
        wall = time.time()
        log12.add(wall, volts, driving, temp_c)
        if len(log12.readings) != n_before:
          last_save = 0.0   # a parking session was just recorded: save now

        # Daily stay-on battery test: keep the comma on past its shutdown timer until it's done
        log12.note_test_done(wall)
        new_hold = log12.hold_wanted(wall)
        if new_hold != hold:
          hold = new_hold
          last_save = 0.0   # save before the comma is allowed to shut down
          try:
            params_memory.put_bool("SmartEco12VHold", hold)
          except Exception:
            cloudlog.exception("battery12vd: hold flag failed")

        warn = params.get_float("SmartEco12VWarn") or 12.2
        drop = log12.drop(params.get_float("SmartEco12VDrain") or 0.10)
        low_status = log12.status(warn)
        new_status = (low_status, drop)
        if new_status != status:
          status = new_status
          try:
            params.put(STATUS_PARAM, str(low_status + (10 if drop is not None else 0)))
            set_offroad_alert(ALERT, low_status == STATUS_LOW)
            set_offroad_alert(ALERT_REPEAT, low_status == STATUS_REPEAT)
            set_offroad_alert(ALERT_COLD, low_status == STATUS_COLD)
            set_offroad_alert(ALERT_DRAIN, drop is not None, f"{drop:.2f}" if drop is not None else None)
          except Exception:
            cloudlog.exception("battery12vd: alert failed")

      if now - last_save > SAVE_EVERY_S:
        last_save = now
        try:
          log12.save()
        except Exception:
          cloudlog.exception("battery12vd: save failed")
      rk.keep_time()
  finally:
    try:
      log12.save()
    except Exception:
      pass


if __name__ == "__main__":
  main()
