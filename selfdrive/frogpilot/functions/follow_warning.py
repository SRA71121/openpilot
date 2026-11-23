"""Following-too-close warning (Smart Eco fork). Alert only: it never touches steering, gas or brakes.

Fires when the time gap to the lead car stays under the driver's chosen gap for HOLD_S seconds while
moving above a minimum speed. Turn signal on (passing or merging) and standstill suppress it. After it
fires it stays quiet for COOLDOWN_S so it nags at most once per stretch.
"""

HOLD_S = 2.0
COOLDOWN_S = 30.0
MIN_LEAD_DIST = 1.0  # m, ignore nonsense readings


class FollowWarning:
  def __init__(self):
    self.close_t = 0.0
    self.cooldown = 0.0

  def update(self, dt: float, enabled: bool, v_ego: float, lead_status: bool, d_rel: float,
             gap_s: float, min_speed: float, blinker: bool, standstill: bool) -> bool:
    self.cooldown = max(0.0, self.cooldown - dt)

    watching = enabled and lead_status and not blinker and not standstill and \
               v_ego >= max(min_speed, 1.0) and d_rel > MIN_LEAD_DIST
    if watching and d_rel / v_ego < gap_s:
      self.close_t += dt
    else:
      self.close_t = 0.0

    if self.close_t >= HOLD_S and self.cooldown <= 0.0:
      self.close_t = 0.0
      self.cooldown = COOLDOWN_S
      return True
    return False
