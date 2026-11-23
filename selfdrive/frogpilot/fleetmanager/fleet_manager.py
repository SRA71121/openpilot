#!/usr/bin/env python3
# otisserv - Copyright (c) 2019-, Rick Lan, dragonpilot community, and a number of other of contributors.
# Fleet Manager - [actuallylemoncurd](https://github.com/actuallylemoncurd), [AlexandreSato](https://github.com/alexandreSato), [ntegan1](https://github.com/ntegan1), [royjr](https://github.com/royjr), and [sunnyhaibin] (https://github.com/sunnypilot)
# Almost everything else - ChatGPT
# dirty PR pusher - mike8643
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import os
import random
import secrets
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, Response, request, send_from_directory, session, redirect, url_for
import requests
from requests.exceptions import ConnectionError
from openpilot.common.realtime import set_core_affinity
import openpilot.selfdrive.frogpilot.fleetmanager.helpers as fleet
from openpilot.system.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog
import traceback

app = Flask(__name__)

@app.route("/")
def home_page():
  return render_template("index.html")

@app.errorhandler(500)
def internal_error(exception):
  print('500 error caught')
  tberror = traceback.format_exc()
  return render_template("error.html", error=tberror)

@app.route("/footage/full/<cameratype>/<route>")
def full(cameratype, route):
  chunk_size = 1024 * 512  # 5KiB
  file_name = cameratype + (".ts" if cameratype == "qcamera" else ".hevc")
  vidlist = "|".join(Paths.log_root() + "/" + segment + "/" + file_name for segment in fleet.segments_in_route(route))

  def generate_buffered_stream():
    with fleet.ffmpeg_mp4_concat_wrap_process_builder(vidlist, cameratype, chunk_size) as process:
      for chunk in iter(lambda: process.stdout.read(chunk_size), b""):
        yield bytes(chunk)
  return Response(generate_buffered_stream(), status=200, mimetype='video/mp4')


@app.route("/footage/<cameratype>/<segment>")
def fcamera(cameratype, segment):
  if not fleet.is_valid_segment(segment):
    return render_template("error.html", error="invalid segment")
  file_name = Paths.log_root() + "/" + segment + "/" + cameratype + (".ts" if cameratype == "qcamera" else ".hevc")
  return Response(fleet.ffmpeg_mp4_wrap_process_builder(file_name).stdout.read(), status=200, mimetype='video/mp4')


@app.route("/footage/<route>")
def route(route):
  if len(route) != 20:
    return render_template("error.html", error="route not found")

  if str(request.query_string) == "b''":
    query_segment = str("0")
    query_type = "qcamera"
  else:
    query_segment = (str(request.query_string).split(","))[0][2:]
    query_type = (str(request.query_string).split(","))[1][:-1]

  links = ""
  segments = ""
  for segment in fleet.segments_in_route(route):
    links += "<a href='"+route+"?"+segment.split("--")[2]+","+query_type+"'>"+segment+"</a><br>"
    segments += "'"+segment+"',"
  return render_template("route.html", route=route, query_type=query_type, links=links, segments=segments, query_segment=query_segment)


@app.route("/footage/")
@app.route("/footage")
def footage():
  route_paths = fleet.all_routes()
  gifs = []
  for route_path in route_paths:
    input_path = Paths.log_root() + route_path + "--0/qcamera.ts"
    output_path = Paths.log_root() + route_path + "--0/preview.gif"
    fleet.video_to_img(input_path, output_path)
    gif_path = route_path + "--0/preview.gif"
    gifs.append(gif_path)
  zipped = zip(route_paths, gifs)
  return render_template("footage.html", zipped=zipped)

@app.route("/preserved/")
@app.route("/preserved")
def preserved():
  query_type = "qcamera"
  route_paths = []
  gifs = []
  segments = fleet.preserved_routes()
  for segment in segments:
    input_path = Paths.log_root() + segment + "/qcamera.ts"
    output_path = Paths.log_root() + segment + "/preview.gif"
    fleet.video_to_img(input_path, output_path)
    split_segment = segment.split("--")
    route_paths.append(f"{split_segment[0]}--{split_segment[1]}?{split_segment[2]},{query_type}")
    gif_path = segment + "/preview.gif"
    gifs.append(gif_path)

  zipped = zip(route_paths, gifs, segments)
  return render_template("preserved.html", zipped=zipped)

@app.route("/screenrecords/")
@app.route("/screenrecords")
def screenrecords():
  rows = fleet.list_file(fleet.SCREENRECORD_PATH)
  if not rows:
    return render_template("error.html", error="no screenrecords found at:<br><br>" + fleet.SCREENRECORD_PATH)
  return render_template("screenrecords.html", rows=rows, clip=rows[0])


@app.route("/screenrecords/<clip>")
def screenrecord(clip):
  return render_template("screenrecords.html", rows=fleet.list_files(fleet.SCREENRECORD_PATH), clip=clip)


@app.route("/screenrecords/play/pipe/<file>")
def videoscreenrecord(file):
  file_name = fleet.SCREENRECORD_PATH + file
  return Response(fleet.ffplay_mp4_wrap_process_builder(file_name).stdout.read(), status=200, mimetype='video/mp4')


@app.route("/screenrecords/download/<clip>")
def download_file(clip):
  return send_from_directory(fleet.SCREENRECORD_PATH, clip, as_attachment=True)


@app.route("/about")
def about():
  return render_template("about.html")


@app.route("/error_logs")
def error_logs():
  rows = fleet.list_file(fleet.ERROR_LOGS_PATH)
  if not rows:
    return render_template("error.html", error="no error logs found at:<br><br>" + fleet.ERROR_LOGS_PATH)
  return render_template("error_logs.html", rows=rows)


@app.route("/error_logs/<file_name>")
def open_error_log(file_name):
  f = open(fleet.ERROR_LOGS_PATH + file_name)
  error = f.read()
  return render_template("error_log.html", file_name=file_name, file_content=error)

@app.route("/addr_input", methods=['GET', 'POST'])
def addr_input():
  preload = fleet.preload_favs()
  SearchInput = fleet.get_SearchInput()
  token = fleet.get_public_token()
  s_token = fleet.get_app_token()
  gmap_key = fleet.get_gmap_key()
  PrimeType = fleet.get_PrimeType()
  lon = float(0.0)
  lat = float(0.0)
  if request.method == 'POST':
    valid_addr = False
    postvars = request.form.to_dict()
    addr, lon, lat, valid_addr, token = fleet.parse_addr(postvars, lon, lat, valid_addr, token)
    if not valid_addr:
      # If address is not found, try searching
      postvars = request.form.to_dict()
      addr = request.form.get('addr_val')
      addr, lon, lat, valid_addr, token = fleet.search_addr(postvars, lon, lat, valid_addr, token)
    if valid_addr:
      # If a valid address is found, redirect to nav_confirmation
      return redirect(url_for('nav_confirmation', addr=addr, lon=lon, lat=lat))
    else:
      return render_template("error.html")
  elif PrimeType != 0:
    return render_template("prime.html")
  # amap stuff
  elif SearchInput == 1:
    amap_key, amap_key_2 = fleet.get_amap_key()
    if amap_key == "" or amap_key is None or amap_key_2 == "" or amap_key_2 is None:
      return redirect(url_for('amap_key_input'))
    elif token == "" or token is None:
      return redirect(url_for('public_token_input'))
    elif s_token == "" or s_token is None:
      return redirect(url_for('app_token_input'))
    else:
      return redirect(url_for('amap_addr_input'))
  elif fleet.get_nav_active():
    if SearchInput == 2:
      return render_template("nonprime.html", gmap_key=gmap_key, lon=lon, lat=lat, home=preload[0], work=preload[1], fav1=preload[2], fav2=preload[3], fav3=preload[4])
    else:
      return render_template("nonprime.html", gmap_key=None, lon=None, lat=None, home=preload[0], work=preload[1], fav1=preload[2], fav2=preload[3], fav3=preload[4])
  elif token == "" or token is None:
    return redirect(url_for('public_token_input'))
  elif s_token == "" or s_token is None:
    return redirect(url_for('app_token_input'))
  elif SearchInput == 2:
    lon, lat = fleet.get_last_lon_lat()
    if gmap_key == "" or gmap_key is None:
      return redirect(url_for('gmap_key_input'))
    else:
      return render_template("addr.html", gmap_key=gmap_key, lon=lon, lat=lat, home=preload[0], work=preload[1], fav1=preload[2], fav2=preload[3], fav3=preload[4])
  else:
      return render_template("addr.html", gmap_key=None, lon=None, lat=None, home=preload[0], work=preload[1], fav1=preload[2], fav2=preload[3], fav3=preload[4])

@app.route("/nav_confirmation", methods=['GET', 'POST'])
def nav_confirmation():
  token = fleet.get_public_token()
  lon = request.args.get('lon')
  lat = request.args.get('lat')
  addr = request.args.get('addr')
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.nav_confirmed(postvars)
    return redirect(url_for('addr_input'))
  else:
    return render_template("nav_confirmation.html", addr=addr, lon=lon, lat=lat, token=token)

@app.route("/public_token_input", methods=['GET', 'POST'])
def public_token_input():
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.public_token_input(postvars)
    return redirect(url_for('addr_input'))
  else:
    return render_template("public_token_input.html")

@app.route("/app_token_input", methods=['GET', 'POST'])
def app_token_input():
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.app_token_input(postvars)
    return redirect(url_for('addr_input'))
  else:
    return render_template("app_token_input.html")

@app.route("/gmap_key_input", methods=['GET', 'POST'])
def gmap_key_input():
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.gmap_key_input(postvars)
    return redirect(url_for('addr_input'))
  else:
    return render_template("gmap_key_input.html")

@app.route("/amap_key_input", methods=['GET', 'POST'])
def amap_key_input():
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.amap_key_input(postvars)
    return redirect(url_for('amap_addr_input'))
  else:
    return render_template("amap_key_input.html")

@app.route("/amap_addr_input", methods=['GET', 'POST'])
def amap_addr_input():
  if request.method == 'POST':
    postvars = request.form.to_dict()
    fleet.nav_confirmed(postvars)
    return redirect(url_for('amap_addr_input'))
  else:
    lon, lat = fleet.get_last_lon_lat()
    amap_key, amap_key_2 = fleet.get_amap_key()
    return render_template("amap_addr_input.html", lon=lon, lat=lat, amap_key=amap_key, amap_key_2=amap_key_2)

@app.route("/CurrentStep.json", methods=['GET'])
def find_CurrentStep():
  directory = "/data/openpilot/selfdrive/manager/"
  filename = "CurrentStep.json"
  return send_from_directory(directory, filename, as_attachment=True)

@app.route("/navdirections.json", methods=['GET'])
def find_nav_directions():
  directory = "/data/openpilot/selfdrive/manager/"
  filename = "navdirections.json"
  return send_from_directory(directory, filename, as_attachment=True)

@app.route("/locations", methods=['GET'])
def get_locations():
  data = fleet.get_locations()
  return Response(data, content_type="application/json")

@app.route("/set_destination", methods=['POST'])
def set_destination():
  valid_addr = False
  postvars = request.get_json()
  data, valid_addr = fleet.set_destination(postvars, valid_addr)
  if valid_addr:
    return Response('{"success": true}', content_type='application/json')
  else:
    return Response('{"success": false}', content_type='application/json')

@app.route("/navigation/<file_name>", methods=['GET'])
def find_navicon(file_name):
  directory = "/data/openpilot/selfdrive/assets/navigation/"
  return send_from_directory(directory, file_name, as_attachment=True)

@app.route("/previewgif/<path:file_path>", methods=['GET'])
def find_previewgif(file_path):
  directory = "/data/media/0/realdata/"
  return send_from_directory(directory, file_path, as_attachment=True)

@app.route("/tools", methods=['GET'])
def tools_route():
  return render_template("tools.html")

@app.route("/get_toggle_values", methods=['GET'])
def get_toggle_values_route():
  toggle_values = fleet.get_all_toggle_values()
  return jsonify(toggle_values)

@app.route("/store_toggle_values", methods=['POST'])
def store_toggle_values_route():
  try:
    updated_values = request.get_json()
    fleet.store_toggle_values(updated_values)
    return jsonify({"message": "Values updated successfully"}), 200
  except Exception as e:
    return jsonify({"error": "Failed to update values", "details": str(e)}), 400

# ---- Smart Eco Cruise: trips, leaderboards, speed vs power -------------------
from openpilot.selfdrive.frogpilot.functions import smart_eco_trips as eco_trips
from openpilot.selfdrive.frogpilot.functions.smart_eco_12v import Battery12VLog, battery_summaries, load_history


def _eco_context():
  trips = eco_trips.load_trips()
  routes = eco_trips.load_routes()
  miles = sum(t["miles"] for t in trips)
  drive = sum(t["drive_kwh"] for t in trips)
  totals = {"trips": len(trips), "miles": miles, "drive_kwh": drive,
            "mi_per_kwh": miles / drive if drive > 0.01 else None,
            "won_back_kwh": sum(t["won_back_kwh"] for t in trips),
            "lost_kwh": sum(t["lost_kwh"] for t in trips)}
  return trips, routes, totals


def _max_kw(rows):
  return max([r["steady_kw"] or 0 for r in rows] + [1.0])


@app.route("/smart_eco", methods=["GET"])
def smart_eco_page():
  trips, routes, totals = _eco_context()
  rows = eco_trips.speed_table([t["bins"] for t in trips])
  names = {r["id"]: r["name"] for r in routes}
  return render_template("smart_eco.html", trip=None, totals=totals,
                         boards=eco_trips.leaderboards(trips, routes), recent=trips[:20],
                         route_names=names, speed_rows=rows, max_kw=_max_kw(rows),
                         seasons=eco_trips.season_stats(trips, routes),
                         journeys=eco_trips.journeys(trips, names)[:10],
                         v12=_v12_context())


def _v12_context():
  log12 = Battery12VLog.load()
  warn = fleet.params.get_float("SmartEco12VWarn") or 12.2
  trusted = log12.trusted()[-60:]
  chart = None
  if len(trusted) >= 2:
    vmin, vmax = 11.6, 13.6
    t0, t1 = trusted[0][0], max(trusted[-1][0], trusted[0][0] + 1)
    def xy(r):
      return (round(590 * (r[0] - t0) / (t1 - t0) + 5, 1), round(150 * (1 - (min(max(r[1], vmin), vmax) - vmin) / (vmax - vmin)) + 5, 1))
    pts = [xy(r) for r in trusted]
    chart = {"points": " ".join(f"{x},{y}" for x, y in pts), "dots": pts,
             "warn_y": round(150 * (1 - (min(max(warn, vmin), vmax) - vmin) / (vmax - vmin)) + 5, 1)}
  drain = fleet.params.get_float("SmartEco12VDrain") or 0.10
  return {"latest": log12.latest(), "readings": list(reversed(log12.readings))[:30], "warn": warn, "chart": chart,
          "drain": drain,
          "batteries": battery_summaries(load_history(), log12.readings, warn, drain, time.time()),
          "install_pending": bool(fleet.params.get("SmartEco12VInstallRequest"))}


@app.route("/smart_eco/battery_install", methods=["POST"])
def smart_eco_battery_install():
  # Handed to battery12vd (same path as the button on the comma) so its warnings reset too
  try:
    when = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d")
    epoch = int(when.timestamp()) + 12 * 3600   # midday that date
    btype = request.form.get("type", "").replace("|", " ")[:20]
    note = request.form.get("note", "").replace("|", " ")[:80]
    fleet.params.put("SmartEco12VInstallRequest", f"{epoch}|{btype}|{note}")
  except ValueError:
    pass
  return redirect("/smart_eco#battery")


@app.route("/smart_eco/trip/<int:start>", methods=["GET"])
def smart_eco_trip(start):
  trips, _, _ = _eco_context()
  trip = next((t for t in trips if int(t["start"]) == start), None)
  if trip is None:
    return redirect("/smart_eco")
  rows = eco_trips.speed_table([trip["bins"]])
  return render_template("smart_eco.html", trip=trip, speed_rows=rows, max_kw=_max_kw(rows))


@app.route("/smart_eco/rename", methods=["POST"])
def smart_eco_rename():
  try:
    eco_trips.rename_route(int(request.form.get("id", "0")), request.form.get("name", ""))
  except ValueError:
    pass
  return redirect("/smart_eco")


@app.route("/smart_eco/export.json", methods=["GET"])
def smart_eco_export():
  trips, routes, totals = _eco_context()
  return jsonify({"totals": totals, "routes": routes, "trips": trips,
                  "battery_12v": Battery12VLog.load().to_dict()})


# ---- Car Tools: trouble codes and camera info --------------------------------
from openpilot.selfdrive.frogpilot.functions import car_codes


@app.route("/car_tools", methods=["GET"])
def car_tools_page():
  from openpilot.common.params import Params
  p = Params()
  return render_template("car_tools.html",
                         latest=car_codes.load_latest(),
                         history=list(reversed(car_codes.load_history()))[:20],
                         requested=p.get_bool("CarCodesRequest"),
                         summary=p.get("CarCodesSummary", encoding="utf8") or "",
                         sensor=p.get("CameraSensor", encoding="utf8") or "not seen yet",
                         auto_exposure=p.get_bool("CameraAutoExposure"))


@app.route("/car_tools/request_scan", methods=["POST"])
def car_tools_request_scan():
  from openpilot.common.params import Params
  Params().put_bool("CarCodesRequest", True)
  return redirect("/car_tools")


@app.route("/car_tools/latest.json", methods=["GET"])
def car_tools_latest():
  return jsonify(car_codes.load_latest() or {})


def main():
  try:
    set_core_affinity([0, 1, 2, 3])
  except Exception:
    cloudlog.exception("fleet_manager: failed to set core affinity")
  app.secret_key = secrets.token_hex(32)
  app.run(host="0.0.0.0", port=8082)


if __name__ == '__main__':
  main()
