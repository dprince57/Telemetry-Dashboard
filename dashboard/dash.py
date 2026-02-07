#!/usr/bin/env python3
"""
Pit Wall Server

- Receives telemetry via POST /telemetry
- Cars poll pit commands via GET /pit_command/<car_id>
- Dashboard shows ONLY player cars from PLAYER_CAR_IDS

This UI is defensive: it handles missing fields gracefully.
"""

from flask import Flask, request, jsonify, render_template_string
import sys
from datetime import datetime

app = Flask(__name__)

# ========= CONFIG =========
PLAYER_CAR_IDS = {"0", "1"}   # only show/control these cars

strategy_mode = "manual"      # "manual" or "auto"
TIRE_WEAR_THRESHOLD = 0.70
FUEL_LOW_THRESHOLD = 10.0
MIN_PIT_LAP = 5
MAX_PIT_LAP = 15

# ========= STATE =========
telemetry_data = {}  # car_id -> telemetry dict
pit_commands = {}    # car_id -> command dict
cars_pitted = set()  # for auto mode


# ========= API =========

@app.route("/telemetry", methods=["POST"])
def receive_telemetry():
    data = request.json or {}
    car_id = str(data.get("car_id", ""))

    if not car_id:
        return jsonify({"status": "error", "error": "missing car_id"}), 400

    if "track_position" not in data and "position" in data:
        data["track_position"] = data["position"]
    if "speed_mps" not in data and "velocity_mps" in data:
        data["speed_mps"] = data["velocity_mps"]
    if "in_pit_lane" not in data and "in_pit" in data:
        data["in_pit_lane"] = data["in_pit"]

    data["last_update_iso"] = datetime.now().isoformat()
    telemetry_data[car_id] = data

    if strategy_mode == "auto":
        process_auto_strategy(car_id, data)

    return jsonify({"status": "ok"})


@app.route("/pit_command/<car_id>", methods=["GET"])
def get_pit_command(car_id):
    car_id = str(car_id)
    if car_id in pit_commands:
        cmd = pit_commands[car_id]
        del pit_commands[car_id]
        return jsonify(cmd)
    return jsonify({"should_pit": False})


@app.route("/pit", methods=["POST"])
def send_pit_command():
    data = request.json or {}
    car_id = str(data.get("car_id", ""))

    if not car_id:
        return jsonify({"error": "car_id required"}), 400

    if car_id not in PLAYER_CAR_IDS:
        return jsonify({"error": "not a player car"}), 403

    pit_commands[car_id] = {
        "should_pit": True,
        "change_tires": bool(data.get("change_tires", True)),
        "refuel_amount_kg": float(data.get("refuel_amount_kg", 0.0))
    }

    print(f"[PIT COMMAND] car={car_id} tires={pit_commands[car_id]['change_tires']} fuel={pit_commands[car_id]['refuel_amount_kg']}kg")
    return jsonify({"status": "success", "car_id": car_id})


@app.route("/telemetry_all", methods=["GET"])
def telemetry_all():
    payload = {}
    for cid in sorted(PLAYER_CAR_IDS):
        payload[cid] = telemetry_data.get(cid)
    return jsonify(payload)


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "mode": strategy_mode,
        "cars_tracked": len(telemetry_data),
        "pending_commands": len(pit_commands),
        "cars_pitted": list(cars_pitted)
    })


# ========= AUTO STRATEGY (optional) =========

def process_auto_strategy(car_id, telemetry):
    if car_id not in PLAYER_CAR_IDS:
        return

    if car_id in cars_pitted:
        return

    lap = int(telemetry.get("laps", 0) or 0)
    tire_wear = float(telemetry.get("avg_tire_wear", 0.0) or 0.0)
    fuel = float(telemetry.get("fuel_kg", 999.0) or 999.0)

    if lap < MIN_PIT_LAP or lap > MAX_PIT_LAP:
        return

    should_pit = False
    if tire_wear > TIRE_WEAR_THRESHOLD:
        should_pit = True
        reason = f"tire wear {tire_wear:.1%}"
    elif fuel < FUEL_LOW_THRESHOLD:
        should_pit = True
        reason = f"fuel low {fuel:.1f}kg"
    else:
        reason = ""

    if should_pit:
        pit_commands[car_id] = {
            "should_pit": True,
            "change_tires": True,
            "refuel_amount_kg": 60.0
        }
        cars_pitted.add(car_id)
        print(f"[AUTO PIT] car={car_id} reason={reason}")


# ========= DASHBOARD UI =========

WEB_INTERFACE = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Pit Wall</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root{
      --bg:#0b0f14;
      --text:#d7e0ea;
      --muted:#7f92a8;
      --accent:#39ff88;
      --cyan:#46d3ff;
      --warn:#ffd54a;
      --bad:#ff4d4d;
      --shadow: 0 12px 30px rgba(0,0,0,.45);
      --r:16px;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      background: radial-gradient(1000px 600px at 15% 10%, rgba(57,255,136,.10), transparent 60%),
                  radial-gradient(1000px 600px at 85% 20%, rgba(70,211,255,.10), transparent 55%),
                  var(--bg);
      color:var(--text);
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial;
    }
    .topbar{
      display:flex; align-items:center; justify-content:space-between;
      padding:18px 20px;
      border-bottom:1px solid rgba(255,255,255,.06);
      position:sticky; top:0;
      backdrop-filter: blur(10px);
      background: rgba(11,15,20,.65);
      z-index:20;
    }
    .brand{ display:flex; gap:12px; align-items:center; font-weight:900; letter-spacing:.4px; }
    .dot{ width:10px; height:10px; border-radius:999px; background: var(--accent); box-shadow: 0 0 18px rgba(57,255,136,.35); }
    .sub{ font-size:12px; color:var(--muted); font-weight:600; }
    .pillrow{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .pill{
      padding:6px 10px; border:1px solid rgba(255,255,255,.08);
      border-radius:999px; font-size:12px; color:var(--muted);
      background: rgba(255,255,255,.03);
    }
    .btn{
      border:1px solid rgba(255,255,255,.12);
      background: rgba(255,255,255,.05);
      color:var(--text);
      padding:10px 12px;
      border-radius:12px;
      cursor:pointer;
      font-weight:800;
      transition: .12s transform, .12s background;
    }
    .btn:hover{ background: rgba(255,255,255,.08); transform: translateY(-1px);}
    .btn.danger{
      border-color: rgba(255,77,77,.35);
      background: rgba(255,77,77,.10);
    }
    .btn.danger:hover{ background: rgba(255,77,77,.16); }

    .layout{
      display:grid;
      grid-template-columns: 1.15fr 1fr;
      gap:16px;
      padding:16px;
      max-width: 1400px;
      margin: 0 auto;
    }
    .panel{
      background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.02));
      border:1px solid rgba(255,255,255,.08);
      border-radius: var(--r);
      box-shadow: var(--shadow);
      overflow:hidden;
    }
    .panelHead{
      padding:14px 14px 10px 14px;
      display:flex; align-items:flex-end; justify-content:space-between;
      border-bottom:1px solid rgba(255,255,255,.06);
      background: rgba(255,255,255,.02);
    }
    .panelHead .title{font-weight:900; letter-spacing:.3px;}
    .panelHead .hint{font-size:12px; color:var(--muted); font-weight:700;}
    .panelBody{ padding:14px; }

    .driverCards{ display:grid; gap:12px; }
    .driverCard{
      border:1px solid rgba(255,255,255,.10);
      background: rgba(10,16,25,.55);
      border-radius: 16px;
      padding:12px;
      cursor:pointer;
      transition:.12s transform, .12s border-color, .12s background;
    }
    .driverCard:hover{ transform: translateY(-1px); border-color: rgba(70,211,255,.35); }
    .driverCard.active{ border-color: rgba(57,255,136,.45); background: rgba(57,255,136,.06); }

    .row{display:flex; align-items:center; justify-content:space-between; gap:10px;}
    .name{display:flex; align-items:center; gap:10px; font-weight:900;}
    .badge{
      font-size:11px; font-weight:900;
      padding:4px 8px; border-radius:999px;
      border:1px solid rgba(255,255,255,.10);
      color: var(--muted);
      background: rgba(255,255,255,.03);
    }
    .kpiRow{display:grid; grid-template-columns: repeat(4,1fr); gap:10px; margin-top:10px;}
    .kpi{
      background: rgba(255,255,255,.03);
      border:1px solid rgba(255,255,255,.08);
      border-radius: 14px;
      padding:10px;
    }
    .kpi .lab{font-size:11px; color:var(--muted); font-weight:800;}
    .kpi .val{font-size:16px; font-weight:950; margin-top:2px;}

    .bar{
      margin-top:10px;
      height:10px; border-radius:999px;
      background: rgba(255,255,255,.06);
      overflow:hidden;
      border:1px solid rgba(255,255,255,.08);
    }
    .bar > i{ display:block; height:100%; width:0%; background: var(--accent); }

    /* tires */
    .tiresRow{ margin-top:10px; display:grid; grid-template-columns: repeat(4, 1fr); gap:10px;}
    .tireBox{
      border-radius: 14px;
      padding:10px;
      border:1px solid rgba(255,255,255,.10);
      background: rgba(0,0,0,.16);
      min-height: 56px;
    }
    .tireName{ font-size:11px; color:var(--muted); font-weight:900; }
    .tireVals{ margin-top:4px; display:flex; justify-content:space-between; gap:8px; font-weight:950; }
    .tireVals span{ font-size:13px; }
    .tireGood{ border-color: rgba(57,255,136,.45); }
    .tireWarn{ border-color: rgba(255,213,74,.45); }
    .tireBad{  border-color: rgba(255,77,77,.45); }

    .mapWrap{
      height: 420px;
      background: radial-gradient(600px 350px at 30% 20%, rgba(70,211,255,.10), transparent 55%),
                  radial-gradient(600px 350px at 70% 80%, rgba(57,255,136,.08), transparent 60%),
                  rgba(255,255,255,.02);
      border:1px solid rgba(255,255,255,.08);
      border-radius: 16px;
      overflow:hidden;
      position:relative;
    }
    svg{ width:100%; height:100%; display:block; }
    .trackPath{ fill:none; stroke: rgba(255,255,255,.22); stroke-width: 10; stroke-linecap: round; stroke-linejoin: round; }
    .trackGlow{ fill:none; stroke: rgba(70,211,255,.14); stroke-width: 18; stroke-linecap: round; stroke-linejoin: round; filter: blur(2px); }
    .carDot{ r: 7; stroke: rgba(0,0,0,.45); stroke-width: 2; }
    .legend{
      position:absolute; left:12px; bottom:12px;
      display:flex; gap:10px; align-items:center; flex-wrap:wrap;
      padding:8px 10px;
      border-radius: 14px;
      border:1px solid rgba(255,255,255,.08);
      background: rgba(0,0,0,.25);
      color: var(--muted);
      font-size:12px; font-weight:800;
    }
    .lg{display:flex; align-items:center; gap:6px;}
    .sw{ width:10px; height:10px; border-radius:999px; background: var(--accent); box-shadow: 0 0 14px rgba(57,255,136,.25); }
    .sw.cyan{ background: var(--cyan); box-shadow: 0 0 14px rgba(70,211,255,.25); }

    .rightGrid{ display:grid; grid-template-rows: 1fr; gap:16px; }
    .profile{
      border:1px solid rgba(255,255,255,.08);
      background: rgba(255,255,255,.03);
      border-radius: 16px;
      padding:12px;
    }
    .profileTop{ display:flex; gap:12px; align-items:center; }
    .avatar{
      width:52px; height:52px; border-radius: 14px;
      background: rgba(255,255,255,.06);
      border:1px solid rgba(255,255,255,.10);
      display:flex; align-items:center; justify-content:center;
      font-weight:950; color: var(--cyan);
    }
    .pname{font-weight:950; font-size:16px;}
    .pmuted{font-size:12px; color:var(--muted); font-weight:700;}
    .profileStats{ margin-top:12px; display:grid; grid-template-columns: repeat(3,1fr); gap:10px; }
    .mini{
      border-radius: 14px; padding:10px;
      border:1px solid rgba(255,255,255,.08);
      background: rgba(0,0,0,.18);
    }
    .mini .lab{font-size:11px; color:var(--muted); font-weight:800;}
    .mini .val{font-size:14px; font-weight:950; margin-top:2px;}

    .chartBox{
      margin-top:12px;
      height: 220px;
      border:1px solid rgba(255,255,255,.08);
      background: rgba(255,255,255,.03);
      border-radius: 16px;
      padding:12px;
      display:flex; flex-direction:column; gap:10px;
    }
    canvas{ width:100%; height: 170px; }
  </style>
</head>

<body>
  <div class="topbar">
    <div class="brand">
      <span class="dot"></span>
      <div>
        <div>PIT WALL</div>
        <div class="sub">2-driver dashboard • tires + map movement</div>
      </div>
    </div>

    <div class="pillrow">
      <div class="pill">Mode: <b style="color:var(--text)">{{mode}}</b></div>
      <div class="pill">Cars: <b style="color:var(--text)" id="carsTracked">2</b></div>
      <div class="pill" id="updatedAt">waiting…</div>
      <button class="btn danger" onclick="pitAllCars()">PIT ALL (players)</button>
    </div>
  </div>

  <div class="layout">
    <!-- LEFT -->
    <div class="panel">
      <div class="panelHead">
        <div>
          <div class="title">Telemetry</div>
          <div class="hint">driver summaries + track map</div>
        </div>
        <div class="hint">only cars {{players}}</div>
      </div>
      <div class="panelBody">
        <div class="driverCards" id="driverCards"></div>

        <div style="height:14px"></div>

        <div class="mapWrap">
          <svg viewBox="0 0 900 520">
            <path id="trackPathGlow" class="trackGlow"
              d="M140,300
                 C140,190 230,120 340,140
                 C420,155 450,220 510,220
                 C610,220 640,150 725,165
                 C820,185 835,285 760,330
                 C690,372 645,305 585,330
                 C520,360 525,435 440,425
                 C350,415 355,330 285,330
                 C220,330 200,390 160,395
                 C120,400 110,355 140,300 Z"/>
            <path id="trackPath" class="trackPath"
              d="M140,300
                 C140,190 230,120 340,140
                 C420,155 450,220 510,220
                 C610,220 640,150 725,165
                 C820,185 835,285 760,330
                 C690,372 645,305 585,330
                 C520,360 525,435 440,425
                 C350,415 355,330 285,330
                 C220,330 200,390 160,395
                 C120,400 110,355 140,300 Z"/>

            <circle id="dot0" class="carDot" cx="0" cy="0" fill="var(--accent)"></circle>
            <circle id="dot1" class="carDot" cx="0" cy="0" fill="var(--cyan)"></circle>
          </svg>

          <div class="legend">
            <div class="lg"><span class="sw"></span> Car 0</div>
            <div class="lg"><span class="sw cyan"></span> Car 1</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT -->
    <div class="rightGrid">
      <div class="panel">
        <div class="panelHead">
          <div>
            <div class="title">Driver Profile</div>
            <div class="hint">selected car deep-dive</div>
          </div>
          <div class="hint" id="selectedLabel">selected: 0</div>
        </div>
        <div class="panelBody">
          <div class="profile">
            <div class="profileTop">
              <div class="avatar" id="avatar">D0</div>
              <div>
                <div class="pname" id="pname">Driver 0</div>
                <div class="pmuted" id="pmeta">waiting for telemetry…</div>
              </div>
            </div>

            <div class="profileStats">
              <div class="mini"><div class="lab">Speed</div><div class="val" id="pSpeed">--</div></div>
              <div class="mini"><div class="lab">Lap</div><div class="val" id="pLap">--</div></div>
              <div class="mini"><div class="lab">Track Pos</div><div class="val" id="pPos">--</div></div>
            </div>

            <div class="profileStats">
              <div class="mini"><div class="lab">Fuel</div><div class="val" id="pFuel">--</div></div>
              <div class="mini"><div class="lab">G Total</div><div class="val" id="pG">--</div></div>
              <div class="mini"><div class="lab">Pit</div><div class="val" id="pPit">--</div></div>
            </div>

            <div class="tiresRow" id="profileTires"></div>

            <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
              <button class="btn" onclick="sendPitCommand(selectedCarId, true, 50)">PIT (tires + 50kg)</button>
              <button class="btn" onclick="sendPitCommand(selectedCarId, false, 30)">PIT (30kg)</button>
            </div>

            <div class="chartBox">
              <div class="pill">trend: speed (green), fuel (blue), wear (yellow)</div>
              <canvas id="trendCanvas" width="900" height="220"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>

<script>
  // Track length: will be overwritten when telemetry includes lap_length_meter.
  let TRACK_LENGTH_M = 5513.0;

  const PLAYER_ORDER = ["0","1"];
  let selectedCarId = "0";

  const history = {
    "0": { t: [], speed: [], fuel: [], wear: [] },
    "1": { t: [], speed: [], fuel: [], wear: [] },
  };
  const HISTORY_MAX = 180;

  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function fmt(n, d=1){
    if(n === null || n === undefined || Number.isNaN(n)) return "--";
    return Number(n).toFixed(d);
  }

  function get(t, ...keys){
    for(const k of keys){
      if(t && t[k] !== undefined && t[k] !== null) return t[k];
    }
    return null;
  }

  function wearClass(w){
    if(w > 0.85) return "tireBad";
    if(w > 0.70) return "tireWarn";
    return "tireGood";
  }

  function selectDriver(cid){
    selectedCarId = cid;
    document.getElementById("selectedLabel").textContent = "selected: " + cid;
  }

  function tireBoxHTML(label, wear, temp){
    const cls = wearClass(wear);
    const wearPct = clamp01(wear) * 100;
    const tC = temp;
    return `
      <div class="tireBox ${cls}">
        <div class="tireName">${label}</div>
        <div class="tireVals">
          <span>${fmt(wearPct,1)}%</span>
          <span>${(tC===null||tC===undefined) ? "--" : Math.round(Number(tC))}°C</span>
        </div>
      </div>
    `;
  }

  function renderDriverCards(data){
    const wrap = document.getElementById("driverCards");
    let html = "";

    for(const cid of PLAYER_ORDER){
      const t = data[cid];
      const missing = !t;

      // allow both new and old field names
      const speed_mps = missing ? null : Number(get(t, "speed_mps", "velocity_mps") || 0);
      const speedKph = missing ? null : speed_mps * 3.6;
      const fuel = missing ? null : Number(get(t, "fuel_kg") || 0);
      const laps = missing ? null : Number(get(t, "laps") || 0);
      const pos = missing ? null : Number(get(t, "track_position", "position") || 0);

      const wFL = missing ? 0 : Number(get(t, "tire_FL_wear") || 0);
      const wFR = missing ? 0 : Number(get(t, "tire_FR_wear") || 0);
      const wRL = missing ? 0 : Number(get(t, "tire_RL_wear") || 0);
      const wRR = missing ? 0 : Number(get(t, "tire_RR_wear") || 0);
      const avgWear = (wFL+wFR+wRL+wRR)/4;

      const tFL = missing ? null : get(t, "tire_FL_temp_C");
      const tFR = missing ? null : get(t, "tire_FR_temp_C");
      const tRL = missing ? null : get(t, "tire_RL_temp_C");
      const tRR = missing ? null : get(t, "tire_RR_temp_C");

      const g = missing ? null : Number(get(t, "g_total", "g_forces")?.total ?? get(t, "g_total") ?? null);

      const active = (cid === selectedCarId) ? "active" : "";
      const wearPct = clamp01(avgWear) * 100;

      html += `
        <div class="driverCard ${active}" onclick="selectDriver('${cid}')">
          <div class="row">
            <div class="name">
              <span class="badge">CAR ${cid}</span>
              <span style="color:${cid==='0'?'var(--accent)':'var(--cyan)'}; font-weight:950;">Driver ${cid}</span>
            </div>
            <div class="sub">${missing ? "no data" : "live"}</div>
          </div>

          <div class="kpiRow">
            <div class="kpi"><div class="lab">Speed</div><div class="val">${missing ? "--" : fmt(speedKph,1)} <span class="sub">km/h</span></div></div>
            <div class="kpi"><div class="lab">Fuel</div><div class="val">${missing ? "--" : fmt(fuel,1)} <span class="sub">kg</span></div></div>
            <div class="kpi"><div class="lab">Lap</div><div class="val">${missing ? "--" : laps}</div></div>
            <div class="kpi"><div class="lab">Pos</div><div class="val">${missing ? "--" : fmt(pos,0)} <span class="sub">m</span></div></div>
          </div>

          <div class="bar"><i style="width:${wearPct}%; background: var(--accent)"></i></div>
          <div class="sub" style="margin-top:8px;">Avg wear: <b style="color:var(--accent)">${fmt(wearPct,1)}%</b></div>

          <div class="tiresRow">
            ${tireBoxHTML("FL", wFL, tFL)}
            ${tireBoxHTML("FR", wFR, tFR)}
            ${tireBoxHTML("RL", wRL, tRL)}
            ${tireBoxHTML("RR", wRR, tRR)}
          </div>

          <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn" onclick="event.stopPropagation(); sendPitCommand('${cid}', true, 50)">PIT (tires + 50kg)</button>
            <button class="btn" onclick="event.stopPropagation(); sendPitCommand('${cid}', false, 30)">PIT (30kg)</button>
          </div>
        </div>
      `;
    }

    wrap.innerHTML = html;
  }

  function updateProfile(data){
    const t = data[selectedCarId];

    document.getElementById("avatar").textContent = "D" + selectedCarId;
    document.getElementById("pname").textContent = "Driver " + selectedCarId;

    if(!t){
      document.getElementById("pmeta").textContent = "waiting for telemetry…";
      document.getElementById("pSpeed").textContent = "--";
      document.getElementById("pLap").textContent = "--";
      document.getElementById("pPos").textContent = "--";
      document.getElementById("pFuel").textContent = "--";
      document.getElementById("pG").textContent = "--";
      document.getElementById("pPit").textContent = "--";
      document.getElementById("profileTires").innerHTML = "";
      return;
    }

    // update track length if provided
    const lapLen = get(t, "lap_length_meter");
    if(lapLen) TRACK_LENGTH_M = Number(lapLen);

    const speed_mps = Number(get(t, "speed_mps", "velocity_mps") || 0);
    const speedKph = speed_mps * 3.6;
    const fuel = Number(get(t, "fuel_kg") || 0);
    const laps = Number(get(t, "laps") || 0);
    const pos = Number(get(t, "track_position", "position") || 0);
    const inPit = Boolean(get(t, "in_pit_lane", "in_pit") || false);

    const gTotal = get(t, "g_total");
    const g = (gTotal !== null && gTotal !== undefined) ? Number(gTotal) : null;

    document.getElementById("pmeta").textContent = (inPit ? "IN PIT SPEED ZONE" : "ON TRACK");
    document.getElementById("pSpeed").textContent = fmt(speedKph,1) + " km/h";
    document.getElementById("pLap").textContent = laps;
    document.getElementById("pPos").textContent = fmt(pos,0) + " m";
    document.getElementById("pFuel").textContent = fmt(fuel,1) + " kg";
    document.getElementById("pG").textContent = (g === null ? "--" : fmt(g,2) + "G");
    document.getElementById("pPit").textContent = (inPit ? "YES" : "NO");

    const wFL = Number(get(t, "tire_FL_wear") || 0);
    const wFR = Number(get(t, "tire_FR_wear") || 0);
    const wRL = Number(get(t, "tire_RL_wear") || 0);
    const wRR = Number(get(t, "tire_RR_wear") || 0);

    const tFL = get(t, "tire_FL_temp_C");
    const tFR = get(t, "tire_FR_temp_C");
    const tRL = get(t, "tire_RL_temp_C");
    const tRR = get(t, "tire_RR_temp_C");

    document.getElementById("profileTires").innerHTML = `
      ${tireBoxHTML("FL", wFL, tFL)}
      ${tireBoxHTML("FR", wFR, tFR)}
      ${tireBoxHTML("RL", wRL, tRL)}
      ${tireBoxHTML("RR", wRR, tRR)}
    `;
  }

  function updateTrackDots(data){
    const path = document.getElementById("trackPath");
    if(!path || !path.getTotalLength) return;

    const plen = path.getTotalLength();
    for(const cid of PLAYER_ORDER){
      const t = data[cid];
      if(!t) continue;

      const pos = Number(get(t, "track_position", "position") || 0);
      const frac = ((pos % TRACK_LENGTH_M) / TRACK_LENGTH_M);
      const pt = path.getPointAtLength(frac * plen);

      const dot = document.getElementById(cid === "0" ? "dot0" : "dot1");
      if(dot){
        dot.setAttribute("cx", pt.x);
        dot.setAttribute("cy", pt.y);
      }
    }
  }

  function pushHistory(data){
    const now = Date.now() / 1000;
    for(const cid of PLAYER_ORDER){
      const t = data[cid];
      if(!t) continue;

      const speed_mps = Number(get(t, "speed_mps", "velocity_mps") || 0);
      const speed = speed_mps * 3.6;
      const fuel = Number(get(t, "fuel_kg") || 0);

      const wFL = Number(get(t, "tire_FL_wear") || 0);
      const wFR = Number(get(t, "tire_FR_wear") || 0);
      const wRL = Number(get(t, "tire_RL_wear") || 0);
      const wRR = Number(get(t, "tire_RR_wear") || 0);
      const wear = clamp01((wFL+wFR+wRL+wRR)/4) * 100;

      const h = history[cid];
      h.t.push(now);
      h.speed.push(speed);
      h.fuel.push(fuel);
      h.wear.push(wear);

      while(h.t.length > HISTORY_MAX){
        h.t.shift(); h.speed.shift(); h.fuel.shift(); h.wear.shift();
      }
    }
  }

  function drawTrend(){
    const c = document.getElementById("trendCanvas");
    const ctx = c.getContext("2d");
    const w = c.width, h = c.height;

    ctx.clearRect(0,0,w,h);

    const hdata = history[selectedCarId];
    if(!hdata || hdata.t.length < 3){
      ctx.fillStyle = "rgba(215,224,234,.65)";
      ctx.font = "16px system-ui";
      ctx.fillText("waiting for trend data…", 18, 42);
      return;
    }

    const pad = 26;
    const x0 = pad, y0 = pad, x1 = w - pad, y1 = h - pad;

    // grid
    ctx.strokeStyle = "rgba(255,255,255,.06)";
    ctx.lineWidth = 1;
    for(let i=0;i<=4;i++){
      const yy = y0 + (i/4)*(y1-y0);
      ctx.beginPath(); ctx.moveTo(x0,yy); ctx.lineTo(x1,yy); ctx.stroke();
    }

    const tMin = hdata.t[0], tMax = hdata.t[hdata.t.length-1];
    const tx = (t) => x0 + ((t - tMin) / (tMax - tMin)) * (x1 - x0);

    function minmax(arr){
      let mn = Infinity, mx = -Infinity;
      for(const v of arr){ if(v<mn) mn=v; if(v>mx) mx=v; }
      if(!isFinite(mn) || !isFinite(mx)) return [0,1];
      if(mx - mn < 1e-6) mx = mn + 1;
      return [mn,mx];
    }

    function drawSeries(arr, color){
      const [mn,mx] = minmax(arr);
      const yv = (v) => y1 - ((v - mn)/(mx-mn))*(y1-y0);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      for(let i=0;i<arr.length;i++){
        const x = tx(hdata.t[i]);
        const y = yv(arr[i]);
        if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      }
      ctx.stroke();
    }

    drawSeries(hdata.speed, "rgba(57,255,136,.85)");
    drawSeries(hdata.fuel,  "rgba(70,211,255,.85)");
    drawSeries(hdata.wear,  "rgba(255,213,74,.85)");
  }

  function sendPitCommand(carId, changeTires, refuelAmount){
    fetch("/pit", {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ car_id: carId, change_tires: changeTires, refuel_amount_kg: refuelAmount })
    })
    .then(r => r.json())
    .then(_ => {
      const el = document.getElementById("updatedAt");
      el.textContent = "pit command sent";
      setTimeout(()=> el.textContent = "live", 800);
    });
  }

  function pitAllCars(){
    for(const cid of PLAYER_ORDER){
      sendPitCommand(cid, true, 50);
    }
  }

  function updateTelemetry(){
    fetch("/telemetry_all")
      .then(r => r.json())
      .then(data => {
        const now = new Date();
        document.getElementById("updatedAt").textContent = "updated " + now.toLocaleTimeString();
        document.getElementById("carsTracked").textContent = PLAYER_ORDER.length;

        renderDriverCards(data);
        updateProfile(data);
        updateTrackDots(data);

        pushHistory(data);
        drawTrend();
      })
      .catch(_ => {
        document.getElementById("updatedAt").textContent = "disconnected";
      });
  }

  // init
  selectDriver("0");
  setInterval(updateTelemetry, 1000);
  window.onload = updateTelemetry;
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(
        WEB_INTERFACE,
        mode=strategy_mode,
        cars_tracked=len(telemetry_data),
        players=",".join(sorted(PLAYER_CAR_IDS))
    )


def run_server(mode="manual"):
    global strategy_mode
    strategy_mode = mode

    print("=" * 60)
    print("PIT WALL SERVER")
    print("=" * 60)
    print(f"Mode: {strategy_mode}")
    print("Listening on: 0.0.0.0:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    mode = "manual"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    run_server(mode)

