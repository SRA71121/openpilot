# Smart Eco Cruise (v0.1 — monitoring only)

Status: **Phases 2–3.** Computes speed-based eco profiles, battery power (measured or estimated) and
a recommended acceleration ceiling. **Sends no commands to the car.** Nothing in controls or planning
reads its output.

## Files
- `smart_eco.py` – core logic (profiles + hysteresis, power model, HV V×I with sign learning, trip totals)
- `smart_ecod.py` – onroad daemon; publishes `smartEcoState` at 20 Hz (logged to rlog; 1 Hz in qlog)
- `tests/test_smart_eco.py` – unit tests (`python3 selfdrive/frogpilot/functions/tests/test_smart_eco.py`)

## Enable (until the settings toggle lands in Phase 4)
```
echo -n 1 > /data/params/d/SmartEcoCruise   # then reboot or go offroad/onroad
```

## Configure (optional — defaults are used when empty)
`SmartEcoProfiles` (JSON). `max_kw` is the ceiling everything compares against:
```
{"hysteresis_mph": 2.0, "target_rate_kw_s": 2.0, "over_target_margin_kw": 1.0,
 "profiles": [
  {"name": "Residential", "min_mph": 0,  "min_kw": 4,  "max_kw": 5},
  {"name": "Local",       "min_mph": 20, "min_kw": 10, "max_kw": 12},
  {"name": "County",      "min_mph": 40, "min_kw": 12, "max_kw": 16},
  {"name": "Highway",     "min_mph": 55, "min_kw": 18, "max_kw": 25},
  {"name": "High-speed",  "min_mph": 70, "min_kw": 25, "max_kw": 32}]}
```
`SmartEcoModel` (JSON), any subset of:
```
{"mass_kg": null, "payload_kg": 90, "cda_m2": 0.72, "crr": 0.009, "air_density": 1.0,
 "drive_efficiency": 0.88, "regen_efficiency": 0.70, "aux_kw": 0.4, "measured_current_sign": 0}
```
Settings reload live every ~5 s; trip totals are kept.

## Measured power
GM `0x2C7 BECMBatteryVoltageCurrent` is read by a private parser inside `smart_ecod`, so a missing
message can't affect carstate CAN validity. If it isn't seen within 60 s, the daemon stops reading CAN
and uses the estimate. Current sign is learned from ~10 s of clear motoring/regen (or force it with
`measured_current_sign`).

## Viewing
Open a route in Cabana/plotjuggler and plot `smartEcoState/powerKw` vs `targetKw`,
`overTarget`, `tripExcessKwh`.
