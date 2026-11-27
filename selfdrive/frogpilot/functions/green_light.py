"""Green light alert gate (Smart Eco fork).

The comma can't see light colors: FrogPilot's "red light" means the driving model wants to stop, and
"green" means it wants to go again. While stopped, the model can flip back and forth, which made the
alert go off repeatedly at the same red light. This gate:
  * alerts at most once per stop (re-arms only after the car actually moves),
  * needs a real stop first (stopped with "red" for STOP_MIN_S),
  * needs the "go" to hold steady for GO_HOLD_S before alerting, so a flicker doesn't count.
"""

STOP_MIN_S = 3.0
GO_HOLD_S = 1.0
MOVING_MS = 1.0  # ~2 mph: the stop is over, re-arm for the next one


class GreenLightGate:
  def __init__(self):
    self.reset()

  def reset(self):
    self.red_t = 0.0
    self.go_t = 0.0
    self.alerted = False

  def update(self, dt: float, red_light: bool, standstill: bool, v_ego: float) -> bool:
    if not standstill:
      if v_ego > MOVING_MS:
        self.reset()
      return False

    if red_light:
      self.red_t += dt
      self.go_t = 0.0
      return False

    self.go_t += dt
    if not self.alerted and self.red_t >= STOP_MIN_S and self.go_t >= GO_HOLD_S:
      self.alerted = True
      return True
    return False
