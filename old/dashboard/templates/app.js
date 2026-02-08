const cfg = window.PITWALL;
const TRACK_LENGTH_M = Number(cfg.track.lap_length_meter || 5513.0);
const PIT_IN = Number(cfg.track.pit_entry_position || 0);
const PIT_OUT = Number(cfg.track.pit_exit_position || 0);

const PLAYER_IDS = cfg.playerIds.map(String);
let selectedCarId = PLAYER_IDS[0] || "0";

const history = {}; // per-car trend
for (const cid of PLAYER_IDS){
  history[cid] = { t: [], speed: [], fuel: [], wear: [] };
}
const HISTORY_MAX = 180;

document.getElementById("playersList").textContent = PLAYER_IDS.join(", ");

document.getElementById("pitAllBtn").addEventListener("click", () => {
  for (const cid of PLAYER_IDS) sendPitCommand(cid, true, 50);
});

document.getElementById("pitTiresFuelBtn").addEventListener("click", () => {
  sendPitCommand(selectedCarId, true, 50);
});
document.getElementById("pitFuelBtn").addEventListener("click", () => {
  sendPitCommand(selectedCarId, false, 30);
});

function clamp01(x){ return Math.max(0, Math.min(1, x)); }
function fmt(n, d=1){
  if(n === null || n === undefined || Number.isNaN(n)) return "--";
  return Number(n).toFixed(d);
}

function wearColorFromPct(p){
  if(p >= 70) return "var(--bad)";
  if(p >= 40) return "var(--warn)";
  return "var(--accent)";
}

// Read telemetry defensively (supports old + new key names)
function readPos(t){ return Number(t?.track_position ?? t?.position ?? 0); }
function readSpeedMps(t){ return Number(t?.speed_mps ?? t?.velocity_mps ?? t?.velocity ?? 0); }
function readFuel(t){ return Number(t?.fuel_kg ?? t?.fuel ?? 0); }
function readLap(t){ return Number(t?.laps ?? t?.lap ?? 0); }
function readG(t){ return (t?.g_total !== undefined ? Number(t.g_total) : null); }
function readInPit(t){ return Boolean(t?.in_pit_lane ?? t?.pit_lane ?? false); }

function tireKey(t, key){
  // expect tire_FL_wear, tire_FL_temp_C etc.
  const v = t?.[key];
  return (v === undefined || v === null) ? null : Number(v);
}

function avgTireWear(t){
  const vals = [
    tireKey(t, "tire_FL_wear"),
    tireKey(t, "tire_FR_wear"),
    tireKey(t, "tire_RL_wear"),
    tireKey(t, "tire_RR_wear")
  ].filter(v => v !== null);

  if(vals.length) return vals.reduce((a,b)=>a+b,0)/vals.length;

  // fallback
  if(t?.avg_tire_wear !== undefined) return Number(t.avg_tire_wear);
  return 0;
}

function selectDriver(cid){
  selectedCarId = String(cid);
  document.getElementById("selectedLabel").textContent = `selected: ${selectedCarId}`;
}

function renderPlayerCards(allData){
  const wrap = document.getElementById("driverCards");
  let html = "";

  for(const cid of PLAYER_IDS){
    const t = allData[cid];
    const missing = !t;

    const speedKph = missing ? null : readSpeedMps(t) * 3.6;
    const fuel = missing ? null : readFuel(t);
    const laps = missing ? null : readLap(t);
    const g = missing ? null : readG(t);
    const wear = missing ? 0 : avgTireWear(t);
    const wearPct = clamp01(wear) * 100;
    const col = wearColorFromPct(wearPct);

    const active = (cid === selectedCarId) ? "active" : "";

    html += `
      <div class="driverCard ${active}" onclick="selectDriver('${cid}')">
        <div class="row">
          <div class="name">
            <span class="badge">CAR ${cid}</span>
            <span style="color:${cid===PLAYER_IDS[0]?'var(--accent)':'var(--cyan)'}; font-weight:950;">Driver ${cid}</span>
          </div>
          <div class="sub">${missing ? "no data" : "live"}</div>
        </div>

        <div class="kpiRow">
          <div class="kpi"><div class="lab">Speed</div><div class="val">${missing ? "--" : fmt(speedKph,1)} <span class="sub">km/h</span></div></div>
          <div class="kpi"><div class="lab">Fuel</div><div class="val">${missing ? "--" : fmt(fuel,1)} <span class="sub">kg</span></div></div>
          <div class="kpi"><div class="lab">Lap</div><div class="val">${missing ? "--" : laps}</div></div>
          <div class="kpi"><div class="lab">G Total</div><div class="val">${missing || g===null ? "--" : fmt(g,2)}G</div></div>
        </div>

        <div class="bar"><i style="width:${wearPct}%; background:${col}"></i></div>
        <div class="sub" style="margin-top:8px;">Tire wear: <b style="color:${col}">${fmt(wearPct,1)}%</b></div>
      </div>
    `;
  }

  wrap.innerHTML = html;
  window.selectDriver = selectDriver; // so onclick works
}

function updateProfile(allData){
  const t = allData[selectedCarId];

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
    renderTires(null);
    return;
  }

  const speedKph = readSpeedMps(t) * 3.6;
  const laps = readLap(t);
  const pos = readPos(t);
  const fuel = readFuel(t);
  const g = readG(t);
  const inPit = readInPit(t);

  document.getElementById("pmeta").textContent = inPit ? "IN PIT SPEED ZONE" : "ON TRACK";
  document.getElementById("pSpeed").textContent = fmt(speedKph,1) + " km/h";
  document.getElementById("pLap").textContent = laps;
  document.getElementById("pPos").textContent = fmt(pos,0) + " m";
  document.getElementById("pFuel").textContent = fmt(fuel,1) + " kg";
  document.getElementById("pG").textContent = (g === null ? "--" : fmt(g,2) + "G");
  document.getElementById("pPit").textContent = inPit ? "YES" : "NO";

  renderTires(t);
}

function renderTires(t){
  const grid = document.getElementById("tireGrid");
  if(!t){
    grid.innerHTML = "";
    return;
  }

  const tires = [
    {name:"FL", wear: tireKey(t,"tire_FL_wear"), temp: tireKey(t,"tire_FL_temp_C")},
    {name:"FR", wear: tireKey(t,"tire_FR_wear"), temp: tireKey(t,"tire_FR_temp_C")},
    {name:"RL", wear: tireKey(t,"tire_RL_wear"), temp: tireKey(t,"tire_RL_temp_C")},
    {name:"RR", wear: tireKey(t,"tire_RR_wear"), temp: tireKey(t,"tire_RR_temp_C")},
  ];

  grid.innerHTML = tires.map(tr => {
    const wearPct = tr.wear === null ? null : clamp01(tr.wear) * 100;
    const col = wearPct === null ? "rgba(255,255,255,.10)" : wearColorFromPct(wearPct);
    const wearTxt = wearPct === null ? "--" : fmt(wearPct,1) + "%";
    const tempTxt = tr.temp === null ? "--" : Math.round(tr.temp) + "°C";
    return `
      <div class="tire" style="border-color:${col}">
        <div class="tireTop">
          <div class="tireName">${tr.name}</div>
          <div class="tireWear">${wearTxt}</div>
        </div>
        <div class="tireMeta">Temp: ${tempTxt}</div>
      </div>
    `;
  }).join("");
}

function sendPitCommand(carId, changeTires, refuelAmount){
  fetch("/pit", {
    method:"POST",
    headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ car_id: String(carId), change_tires: changeTires, refuel_amount_kg: refuelAmount })
  }).then(() => {
    const el = document.getElementById("updatedAt");
    el.textContent = "pit command sent";
    setTimeout(()=> el.textContent = "live", 800);
  });
}

// --- MAP: dynamic dots + pit markers ---
function updateTrackMap(allData){
  const path = document.getElementById("trackPath");
  const layer = document.getElementById("dotsLayer");
  if(!path || !path.getTotalLength || !layer) return;

  const plen = path.getTotalLength();

  // Place pit entry/exit markers (once)
  placeMarkerOnPath(path, plen, PIT_IN, "pitEntryDot", "pitEntryText", "PIT IN");
  placeMarkerOnPath(path, plen, PIT_OUT, "pitExitDot", "pitExitText", "PIT OUT");

  // Create/update dots for ALL cars
  const carIds = Object.keys(allData).filter(cid => allData[cid]);

  for(const cid of carIds){
    const id = "dot_" + cid;
    let dot = document.getElementById(id);

    if(!dot){
      dot = document.createElementNS("http://www.w3.org/2000/svg","circle");
      dot.setAttribute("id", id);
      dot.setAttribute("class", "carDot");

      const isPlayer = PLAYER_IDS.includes(String(cid));
      if(String(cid) === PLAYER_IDS[0]){
        dot.setAttribute("fill", "var(--accent)");
        dot.setAttribute("r", "7");
      } else if(String(cid) === PLAYER_IDS[1]){
        dot.setAttribute("fill", "var(--cyan)");
        dot.setAttribute("r", "7");
      } else if(isPlayer){
        dot.setAttribute("fill", "rgba(200,255,220,.65)");
        dot.setAttribute("r", "6");
      } else {
        dot.setAttribute("fill", "rgba(220,230,240,.35)");
        dot.setAttribute("r", "4");
        dot.setAttribute("stroke", "rgba(0,0,0,.25)");
        dot.setAttribute("stroke-width", "1.5");
      }

      layer.appendChild(dot);
    }

    const t = allData[cid];
    const pos = readPos(t);
    const frac = ((pos % TRACK_LENGTH_M) / TRACK_LENGTH_M);
    const pt = path.getPointAtLength(frac * plen);

    dot.setAttribute("cx", pt.x);
    dot.setAttribute("cy", pt.y);
  }
}

function placeMarkerOnPath(path, plen, trackPos, dotId, textId, label){
  const frac = ((trackPos % TRACK_LENGTH_M) / TRACK_LENGTH_M);
  const pt = path.getPointAtLength(frac * plen);

  const d = document.getElementById(dotId);
  const tx = document.getElementById(textId);
  if(!d || !tx) return;

  d.setAttribute("cx", pt.x);
  d.setAttribute("cy", pt.y);

  tx.textContent = label;
  tx.setAttribute("x", pt.x + 12);
  tx.setAttribute("y", pt.y - 10);
}

function pushHistory(allData){
  const now = Date.now() / 1000;
  for(const cid of PLAYER_IDS){
    const t = allData[cid];
    if(!t) continue;

    const speed = readSpeedMps(t) * 3.6;
    const fuel = readFuel(t);
    const wear = clamp01(avgTireWear(t)) * 100;

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

async function tick(){
  try{
    const r = await fetch("/telemetry_all");
    const allData = await r.json();

    document.getElementById("carsTracked").textContent = Object.keys(allData).length;
    document.getElementById("updatedAt").textContent = "updated " + (new Date()).toLocaleTimeString();

    renderPlayerCards(allData);
    updateProfile(allData);
    updateTrackMap(allData);

    pushHistory(allData);
    drawTrend();
  }catch(e){
    document.getElementById("updatedAt").textContent = "disconnected";
  }
}

// init
selectDriver(selectedCarId);
document.getElementById("selectedLabel").textContent = `selected: ${selectedCarId}`;

// poll
setInterval(tick, 1000);
window.onload = tick;

