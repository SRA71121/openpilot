"""Following-too-close reminder (Smart Eco fork). Alert only: it never touches steering, gas or brakes.

Two steps, working whether openpilot is engaged, on Always On Lateral, or off:
  YELLOW  time gap under the driver's setting for HOLD_S seconds
  RED     time gap under the red setting, or closing so fast that impact would come within RED_TTC_S
          seconds. Closing fast while accelerating hard skips the wait, so it can jump straight to red.

An active alert stays up until the gap recovers. After it clears, the same level stays quiet for
REARM_S so it reminds rather than nags. Turn signal on (passing or merging) and standstill suppress it.
"""

NONE, YELLOW, RED = 0, 1, 2

HOLD_S = 2.0          # yellow needs this long under the gap
FAST_HOLD_S = 0.3     # debounce when closing fast / accelerating hard
RED_HOLD_S = 0.5
RED_TTC_S = 2.5       # time to collision that counts as red on its own
FAST_TTC_S = 4.0      # closing quickly enough to shorten the yellow wait
HARD_ACCEL = 1.2      # m/s^2, same threshold the trip log calls hard acceleration
SLOWING = -0.7        # m/s^2: already braking for it, so closing speed alone isn't a reason to escalate
REARM_S = 20.0
MIN_LEAD_DIST = 1.0   # m, ignore nonsense readings


class FollowWarning:
  def __init__(self):
    self.level = NONE
    self.yellow_t = 0.0
    self.red_t = 0.0
    self.rearm = {YELLOW: 0.0, RED: 0.0}

  def update(self, dt: float, enabled: bool, v_ego: float, a_ego: float, lead_status: bool, d_rel: float,
             v_lead: float, gap_s: float, red_gap_s: float, min_speed: float, blinker: bool, standstill: bool) -> int:
    for k in self.rearm:
      self.rearm[k] = max(0.0, self.rearm[k] - dt)

    watching = enabled and lead_status and not blinker and not standstill and \
               v_ego >= max(min_speed, 1.0) and d_rel > MIN_LEAD_DIST
    if not watching:
      self._clear()
      return self.level

    gap = d_rel / v_ego
    closing = v_ego - v_lead
    # Closing speed only escalates while the driver/openpilot isn't already slowing down for it,
    # so a normal stop behind traffic doesn't flash red
    ttc = d_rel / closing if closing > 0.1 and a_ego > SLOWING else float("inf")
    fast = ttc < FAST_TTC_S or (a_ego > HARD_ACCEL and closing > 0.5)

    red_now = gap < min(red_gap_s, gap_s) or ttc < RED_TTC_S
    yellow_now = gap < gap_s or red_now

    self.red_t = self.red_t + dt if red_now else 0.0
    self.yellow_t = self.yellow_t + dt if yellow_now else 0.0

    if self.level < RED and self.red_t >= (FAST_HOLD_S if fast else RED_HOLD_S) and self.rearm[RED] <= 0.0:
      self.level = RED
    elif self.level < YELLOW and self.yellow_t >= (FAST_HOLD_S if fast else HOLD_S) and self.rearm[YELLOW] <= 0.0:
      self.level = YELLOW
    elif self.level == RED and not red_now:
      self.rearm[RED] = REARM_S
      self.level = YELLOW if yellow_now else NONE
      if self.level == NONE:
        self.rearm[YELLOW] = REARM_S
    elif self.level == YELLOW and not yellow_now:
      self.rearm[YELLOW] = REARM_S
      self.level = NONE

    return self.level

  def _clear(self):
    if self.level != NONE:
      self.rearm[self.level] = REARM_S
      if self.level == RED:
        self.rearm[YELLOW] = REARM_S
    self.level = NONE
    self.yellow_t = self.red_t = 0.0
