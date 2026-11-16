# Smart Eco Cruise

All settings: **FrogPilot → Controls → Smart Eco Cruise → Manage**. Trip pages: Fleet Manager → **Smart Eco**.

| Feature | What it does | Changes driving? | Default |
|---|---|---|---|
| Logging (`smart_ecod`) | Speed-band profiles, power (estimated, or real HV V×I if 0x2C7 exists), `smartEcoState` at 20 Hz | No | On |
| Trips / leaderboards | Per-drive totals, auto-detected routes, top-5 by driving mi/kWh (heat shown beside), summer vs winter, multi-stop journeys, speed vs kW | No | On |
| Eco score + range | Live 0-10 score vs your band ceiling (smoothed 5 s), trip average, full-pack range at the last few minutes' pace | No | On |
| 12V monitor (`battery12vd`) | Logs 12V while parked/driving, resting & pre-drive voltage, offroad alert below your threshold | No | On |
| Power Ceiling | With openpilot longitudinal: caps max acceleration to the band's kW ceiling; may sag up to N mph on climbs, then holds speed | Yes (accel only) | **Off** |
| Highway Glide | ≥35 mph, no close/slower lead, no curve: coast on descents, float up to +N mph over set speed instead of regen, glide back down | Yes | **Off** |

Safety properties of the two driving features: they only lower the planner's *maximum* acceleration
(never braking/minimum accel), the gas pedal disables both instantly, they're inactive in experimental
mode / without openpilot longitudinal, and all panda/carcontroller limits are untouched.

Band ceilings (kW, min/max) are adjustable on the comma; changes apply within seconds.
Simulated benefit of Highway Glide on rolling terrain is small (~0.5%); real logs will tell.

Tests: `python3 selfdrive/frogpilot/functions/tests/test_smart_eco*.py`
