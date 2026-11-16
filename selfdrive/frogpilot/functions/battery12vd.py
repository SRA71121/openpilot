#!/usr/bin/env python3
"""
battery12vd - Smart Eco 12V battery monitor.

Runs whenever the comma is on (parked or driving) and Smart Eco is enabled. Reads only
peripheralState (12V) and deviceState (driving or parked). Commands nothing.
Shows an offroad alert when the resting voltage drops below "SmartEco12VWarn".
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
SAVE_EVERY_S = 600.0


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
        log12.add(time.time(), volts, driving)

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
