import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from green_light import GreenLightGate  # noqa: E402

DT = 0.01


def run(gate, seconds, red, standstill=True, v=0.0):
  hits = 0
  for _ in range(int(round(seconds / DT))):
    hits += gate.update(DT, red, standstill, v)
  return hits


class TestGreenLight(unittest.TestCase):
  def test_real_green_alerts_once(self):
    g = GreenLightGate()
    run(g, 2.0, False, standstill=False, v=10.0)  # driving up
    self.assertEqual(run(g, 20.0, True), 0)        # waiting at red
    self.assertEqual(run(g, 5.0, False), 1)        # light turns green: one alert

  def test_flicker_while_waiting_never_alerts(self):
    g = GreenLightGate()
    hits = 0
    for _ in range(30):  # model flips stop/go every half second for 30 s
      hits += run(g, 0.5, True)
      hits += run(g, 0.5, False)
    self.assertEqual(hits, 0)

  def test_repeats_at_same_light_suppressed(self):
    g = GreenLightGate()
    run(g, 10.0, True)
    self.assertEqual(run(g, 2.0, False), 1)
    # model changes its mind again while still stopped: no more alerts this stop
    run(g, 5.0, True)
    self.assertEqual(run(g, 5.0, False), 0)

  def test_rearms_after_moving(self):
    g = GreenLightGate()
    run(g, 10.0, True)
    self.assertEqual(run(g, 2.0, False), 1)
    run(g, 5.0, False, standstill=False, v=12.0)  # drove off
    run(g, 10.0, True)                             # next red light
    self.assertEqual(run(g, 2.0, False), 1)

  def test_quick_stop_does_not_alert(self):
    g = GreenLightGate()
    run(g, 1.5, True)  # brief stop (stop sign roll)
    self.assertEqual(run(g, 3.0, False), 0)

  def test_creeping_does_not_rearm(self):
    g = GreenLightGate()
    run(g, 10.0, True)
    self.assertEqual(run(g, 2.0, False), 1)
    run(g, 1.0, False, standstill=False, v=0.5)  # inched forward in the queue
    run(g, 5.0, True)
    self.assertEqual(run(g, 2.0, False), 0)


if __name__ == "__main__":
  unittest.main()
