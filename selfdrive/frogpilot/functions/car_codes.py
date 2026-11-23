"""Read-only trouble code reader for the Smart Eco fork.

Runs only inside the existing fingerprinting window at car start (openpilot not engaged, the panda in
its diagnostic-only ELM327 safety mode), and only when the driver asked for a scan. Nothing here can
send a control message: the panda blocks every address except diagnostics in that mode. Codes are
never cleared.

Three kinds of request are tried, because it is not yet known which ones the Bolt answers on the bus
the comma is wired to:
  * OBD-II modes 03 / 07 / 0A (stored / pending / permanent) broadcast on 0x7DF
  * UDS 0x19 02 (DTCs by status mask) broadcast on 0x7DF
  * GMLAN $A9 81 to the front camera module (0x24B), whose answers come back as single frames on 0x54B
"""
import json
import os
import time

DATA_DIR = "/data/car_codes"
LATEST_FILE = "latest.json"
HISTORY_FILE = "history.json"
HISTORY_MAX = 50

LETTERS = "PCBU"
OBD_MODES = (
  (b"\x03", b"\x43", "stored"),
  (b"\x07", b"\x47", "pending"),
  (b"\x0a", b"\x4a", "permanent"),
)
UDS_REQUEST = b"\x19\x02\xff"
UDS_RESPONSE = b"\x59\x02"
GM_CAMERA_TX = 0x24B
GM_CAMERA_UUDT_RX = 0x54B
GMLAN_DTC_REQUEST = bytes([0x03, 0xA9, 0x81, 0xFF, 0x00, 0x00, 0x00, 0x00])

MODULE_NAMES = {
  0x7E8: "Module 0x7E0",
  0x7E9: "Module 0x7E1",
  0x7EA: "Module 0x7E2",
  0x7EB: "Module 0x7E3",
  0x7EC: "Battery system (0x7E4)",
  0x7ED: "Module 0x7E5",
  0x7EE: "Module 0x7E6",
  0x7EF: "Module 0x7E7",
  GM_CAMERA_UUDT_RX: "Front camera (0x24B)",
}


def decode_dtc(b1: int, b2: int) -> str:
  """Two-byte SAE J2012 code -> 'P0A7F'."""
  return f"{LETTERS[(b1 >> 6) & 0x3]}{(b1 >> 4) & 0x3}{b1 & 0xF:X}{b2 >> 4:X}{b2 & 0xF:X}"


def parse_obd_dtcs(payload: bytes) -> list[str]:
  """Payload after the 0x43/0x47/0x4A byte. ISO 15765-4 puts a count byte first; tolerate both."""
  if len(payload) % 2 == 1:
    count, payload = payload[0], payload[1:]
    payload = payload[:count * 2]
  codes = []
  for i in range(0, len(payload) - 1, 2):
    if payload[i] == 0 and payload[i + 1] == 0:
      continue
    codes.append(decode_dtc(payload[i], payload[i + 1]))
  return codes


def describe_uds_status(status: int) -> str:
  if status & 0x01:
    return "active"
  if status & 0x08:
    return "stored"
  if status & 0x04:
    return "pending"
  return "history"


def parse_uds_dtcs(payload: bytes) -> list[dict]:
  """Payload after 0x59 0x02: availability mask, then 4-byte records (3-byte DTC + status)."""
  out = []
  records = payload[1:]
  for i in range(0, len(records) - 3, 4):
    b1, b2, ftb, status = records[i:i + 4]
    if b1 == 0 and b2 == 0 and ftb == 0:
      continue
    out.append({"code": decode_dtc(b1, b2), "ftb": f"{ftb:02X}", "status": describe_uds_status(status)})
  return out


def parse_gmlan_frames(frames: list[bytes]) -> list[dict]:
  """GMLAN $A9 81 answers: [0x81, dtc_hi, dtc_lo, failure_type, status, ...]; 0x0000 ends the list."""
  out = []
  seen = set()
  for dat in frames:
    if len(dat) < 5 or dat[0] != 0x81:
      continue
    b1, b2, ftb, status = dat[1], dat[2], dat[3], dat[4]
    if b1 == 0 and b2 == 0:
      break
    key = (b1, b2, ftb)
    if key in seen:
      continue
    seen.add(key)
    out.append({"code": decode_dtc(b1, b2), "ftb": f"{ftb:02X}", "status": describe_uds_status(status)})
  return out


def module_name(rx_addr: int) -> str:
  return MODULE_NAMES.get(rx_addr, f"Module 0x{rx_addr:X}")


def summarize(result: dict) -> str:
  """One short line for the comma screen."""
  if result.get("error") and not result.get("modules"):
    return f"Scan failed: {result['error']}"
  codes = sorted({c["code"] + (f"-{c['ftb']}" if c.get("ftb") else "") for m in result.get("modules", []) for c in m["codes"]})
  responded = len(result.get("modules", []))
  if not responded:
    return "No modules answered. This scan method may not reach your car's modules from the camera connector."
  if not codes:
    return f"No trouble codes. {responded} module{'s' if responded != 1 else ''} answered."
  shown = ", ".join(codes[:6]) + (f" +{len(codes) - 6} more" if len(codes) > 6 else "")
  return f"{len(codes)} code{'s' if len(codes) != 1 else ''}: {shown}"


def _merge(modules: dict, rx_addr: int, bus: int, codes: list[dict]):
  key = (rx_addr, bus)
  m = modules.setdefault(key, {"addr": f"0x{rx_addr:X}", "bus": bus, "name": module_name(rx_addr), "codes": []})
  have = {(c["code"], c.get("ftb"), c["status"]) for c in m["codes"]}
  for c in codes:
    k = (c["code"], c.get("ftb"), c["status"])
    if k not in have:
      m["codes"].append(c)
      have.add(k)


def _functional_tx_addrs():
  # Same pattern openpilot's VIN query uses: set up every physical pair so multi-frame answers get flow control
  return [a for a in range(0x700, 0x800) if a != 0x7DF]


def read_codes(logcan, sendcan, buses=(0, 1), timeout=0.15, gmlan_listen=1.0) -> dict:
  """Query and return a result dict. Never raises; errors land in result['error']."""
  import cereal.messaging as messaging
  from panda.python.uds import FUNCTIONAL_ADDRS
  from openpilot.selfdrive.boardd.boardd import can_list_to_can_capnp
  from openpilot.selfdrive.car.isotp_parallel_query import IsoTpParallelQuery

  started = time.monotonic()
  modules: dict = {}
  raw: list[dict] = []
  result = {"time": int(time.time()), "modules": [], "raw": raw, "methods": []}
  try:
    for bus in buses:
      for request, response, label in OBD_MODES:
        q = IsoTpParallelQuery(sendcan, logcan, bus, _functional_tx_addrs(), [request], [response],
                               functional_addrs=FUNCTIONAL_ADDRS)
        for (tx_addr, _), payload in q.get_data(timeout).items():
          rx = tx_addr + 8
          raw.append({"method": f"obd{request.hex()}", "bus": bus, "rx": f"0x{rx:X}", "data": payload.hex()})
          _merge(modules, rx, bus, [{"code": c, "ftb": "", "status": label} for c in parse_obd_dtcs(payload)])
      result["methods"].append(f"obd bus {bus}")

      q = IsoTpParallelQuery(sendcan, logcan, bus, _functional_tx_addrs(), [UDS_REQUEST], [UDS_RESPONSE],
                             functional_addrs=FUNCTIONAL_ADDRS)
      for (tx_addr, _), payload in q.get_data(timeout).items():
        rx = tx_addr + 8
        raw.append({"method": "uds19", "bus": bus, "rx": f"0x{rx:X}", "data": payload.hex()})
        _merge(modules, rx, bus, parse_uds_dtcs(payload))
      result["methods"].append(f"uds bus {bus}")

    # GMLAN front camera on bus 0 (the only GM module address the panda allows in this mode)
    messaging.drain_sock_raw(logcan)
    sendcan.send(can_list_to_can_capnp([[GM_CAMERA_TX, 0, GMLAN_DTC_REQUEST, 0]], msgtype='sendcan'))
    frames = []
    end = time.monotonic() + gmlan_listen
    while time.monotonic() < end:
      for packet in messaging.drain_sock(logcan, wait_for_one=True):
        for msg in packet.can:
          if msg.src == 0 and msg.address == GM_CAMERA_UUDT_RX:
            frames.append(bytes(msg.dat))
    if frames:
      raw.extend({"method": "gmlanA9", "bus": 0, "rx": f"0x{GM_CAMERA_UUDT_RX:X}", "data": f.hex()} for f in frames[:40])
      _merge(modules, GM_CAMERA_UUDT_RX, 0, parse_gmlan_frames(frames))
    result["methods"].append("gmlan camera")
  except Exception as e:  # never let a scan break startup
    result["error"] = f"{type(e).__name__}: {e}"[:200]

  result["modules"] = list(modules.values())
  result["seconds"] = round(time.monotonic() - started, 2)
  return result


def save_result(result: dict, data_dir: str = DATA_DIR) -> None:
  os.makedirs(data_dir, exist_ok=True)
  tmp = os.path.join(data_dir, LATEST_FILE + ".tmp")
  with open(tmp, "w") as f:
    json.dump(result, f)
  os.replace(tmp, os.path.join(data_dir, LATEST_FILE))

  history = load_history(data_dir)
  history.append({k: result[k] for k in ("time", "modules", "error", "seconds") if k in result})
  history = history[-HISTORY_MAX:]
  tmp = os.path.join(data_dir, HISTORY_FILE + ".tmp")
  with open(tmp, "w") as f:
    json.dump(history, f)
  os.replace(tmp, os.path.join(data_dir, HISTORY_FILE))


def load_latest(data_dir: str = DATA_DIR):
  try:
    with open(os.path.join(data_dir, LATEST_FILE)) as f:
      return json.load(f)
  except Exception:
    return None


def load_history(data_dir: str = DATA_DIR) -> list:
  try:
    with open(os.path.join(data_dir, HISTORY_FILE)) as f:
      h = json.load(f)
    return h if isinstance(h, list) else []
  except Exception:
    return []


def run_requested_scan(params, logcan, sendcan, set_obd_multiplexing) -> None:
  """Called from fingerprinting while the panda is still in diagnostic-only mode."""
  try:
    if not params.get_bool("CarCodesRequest"):
      return
    params.remove("CarCodesRequest")
    set_obd_multiplexing(params, True)
    result = read_codes(logcan, sendcan)
    save_result(result)
    summary = summarize(result)
    stamp = time.strftime("%b %d %I:%M %p", time.localtime(result["time"]))
    params.put("CarCodesSummary", f"{stamp}: {summary}")
  except Exception:
    pass
