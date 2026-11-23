# Smart Eco Cruise

All settings: **FrogPilot → Controls → Smart Eco Cruise → Manage**. Trip pages: Fleet Manager → **Smart Eco**.

| Feature | What it does | Changes driving? | Default |
|---|---|---|---|
| Logging (`smart_ecod`) | Speed-band profiles, power (estimated, or real HV V×I if 0x2C7 exists), `smartEcoState` at 20 Hz | No | On |
| Trips / leaderboards | Per-drive totals, auto-detected routes, top-5 by TOTAL driving mi/kWh (events included; "clean" shown beside), summer vs winter, multi-stop journeys | No | On |
| Events | Hard acceleration, passing (hard accel + turn signal ≥40 mph), hard slowing: each logged with time, mph, kWh, energy over ceiling, peak kW | No | On |
| Energy balance | Per trip: won back (regen kWh), lost (kWh above band ceilings), net | No | On |
| Speed vs power | Per 5 mph band: time, avg, steady avg + min/max, accelerating avg, slowing avg, regen kWh, peak/lowest kW | No | On |
| Eco score + range | Live 0-10 score vs your band ceiling (smoothed 5 s), trip average, full-pack range at the last few minutes' pace | No | On |
| 12V health (`battery12vd`) | One reading per park, right before the comma shuts off (shutdown timer = rest time); skips charging, restarts the rest clock after it; <30 min rest flagged; offroad alert below your threshold | No | On |
| Power Ceiling | With openpilot longitudinal: caps max acceleration to the band's kW ceiling; may sag up to N mph on climbs, then holds speed | Yes (accel only) | **Off** |
| Highway Glide | ≥35 mph, no close/slower lead, no curve: coast on descents, float up to +N mph over set speed instead of regen, glide back down | Yes | **Off** |

Safety properties of the two driving features: they only lower the planner's *maximum* acceleration
(never braking/minimum accel), the gas pedal disables both instantly, they're inactive in experimental
mode / without openpilot longitudinal, and all panda/carcontroller limits are untouched.

Band ceilings (kW, min/max) are adjustable on the comma; changes apply within seconds.
Simulated benefit of Highway Glide on rolling terrain is small (~0.5%); real logs will tell.

Tests: `python3 selfdrive/frogpilot/functions/tests/test_smart_eco*.py`

No heater/accessory estimates anywhere. If the car broadcasts its own pack reading (0x2C7), it is shown
as a plain "car's battery total" with no attempt to split out where it went.

## Added Nov 2026

| Feature | Where | Default | Notes |
|---|---|---|---|
| Night Camera Exposure Fix | FrogPilot Visuals | off | March23's OS04C10 driver pins road-camera exposure at 100 lines / gain 0x320 (early bring-up values). This lets auto exposure through, as openpilot 0.9.7 does. Road and wide cameras only; the driver monitoring camera is unchanged. The driving model sees the brighter image. No effect on OX03C10 units. |
| Read Trouble Codes | FrogPilot Vehicles, Fleet Manager → Car Tools | on request | Read-only. Runs once at the next car start inside the existing fingerprinting window, while the panda is in ELM327 (diagnostic-only) safety. Tries OBD-II 03/07/0A and UDS 19 02 on 0x7DF, plus GMLAN A9 81 to the front camera (0x24B → 0x54B). Never clears codes. Panda safety is not changed. |
| Following Too Close Reminder | Smart Eco section | on; yellow 1.0 s, red 0.6 s, above 25 mph | Alert only. Works engaged, on Always On Lateral, or off. Yellow: gap under the yellow setting for 2 s. Red: gap under the red setting, or time to impact under 2.5 s while not already slowing. Closing fast or accelerating hard (>1.2 m/s²) cuts the wait to 0.3 s. Stays up until the gap recovers, then each level re-arms after 20 s. Quiet with a turn signal on or at standstill. Sounds: `back_off.wav` (yellow), `back_off_urgent.wav` (red), both in `assets/random_events/sounds/` (48 kHz mono 16-bit). |
