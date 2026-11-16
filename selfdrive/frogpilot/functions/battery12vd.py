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
from openpilot.selfdrive.frogpilot.functions.smart_eco_12v import Battery12VLog

ALERT = "Offroad_SmartEco12VLow"
SAVE_EVERY_S = 300.0


def main():
  params = Params()
  log12 = Battery12VLog.load()
  sm = messaging.SubMaster(["peripheralState", "deviceState"])
  rk = Ratekeeper(1.0, print_delay_threshold=None)
  last_save = time.monotonic()
  alert_on = False

  def _stop(*_):
    raise SystemExit
  signal.signal(signal.SIGTERM, _stop)

  try:
    while True:
      sm.update(0)
      now = time.monotonic()
      if sm.seen["peripheralState"]:
        volts = sm["peripheralState"].voltage / 1000.0
        driving = bool(sm["deviceState"].started) if sm.seen["deviceState"] else False
        n_before = len(log12.readings)
        log12.add(time.time(), volts, driving)
        if len(log12.readings) != n_before:
          last_save = 0.0   # a parking session was just recorded: save now

        warn = params.get_float("SmartEco12VWarn") or 12.2
        low = log12.low(warn)
        if (low is not None) != alert_on:
          alert_on = low is not None
          try:
            set_offroad_alert(ALERT, alert_on, f"{low:.2f}" if alert_on else None)
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
