import maplibregl from "maplibre-gl";

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const SOURCES = {
  imagery: { type: "raster", tiles: [`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 18, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" },
  places: { type: "raster", tiles: [`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 18 },
  topo: { type: "raster", tiles: [`${ESRI}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 18, attribution: "Map &copy; Esri, HERE, Garmin, USGS, NGA" },
  streets: { type: "raster", tiles: [`${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 18, attribution: "Map &copy; Esri, HERE, Garmin, FAO, NOAA, USGS, OpenStreetMap contributors" },
  dark: { type: "raster", tiles: [`${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 16, attribution: "Map &copy; Esri, HERE, Garmin, OpenStreetMap contributors" },
  darklabels: { type: "raster", tiles: [`${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 16 },
  dem: { type: "raster-dem", tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 14, encoding: "terrarium", attribution: "Elevation: Mapzen, AWS Open Data" },
};
const BASEMAPS = [
  { id: "sat", label: "Satellite", layers: ["imagery", "places"] },
  { id: "topo", label: "Terrain", layers: ["topo"], hill: true },
  { id: "streets", label: "Streets", layers: ["streets"] },
  { id: "dark", label: "Dark", layers: ["dark", "darklabels"] },
];
const HAZ_KM = { Low: 0, Moderate: 10, High: 18, Extreme: 30 };
const HAZ_COLOR = { Low: "#cfe3f2", Moderate: "#7cc4f5", High: "#3a9bea", Extreme: "#1b6fd8" };
const TEAM_COLOR = { boat: "#4da3ff", medical: "#ff7a45", ground: "#2bd4a0" };
const LAYER_CHIPS = [["flood", "Flood extent"], ["roads", "Roads"], ["routes", "Routes"], ["towns", "Town names"], ["teams", "Teams"], ["inc", "Incidents"]];
const DASH_FRAMES = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><path d="M3.5 2h3.2v12H3.5zM9.3 2h3.2v12H9.3z"/></svg>',
  back: '<svg viewBox="0 0 16 16"><path d="M11 2.5v11L4 8zM3 2h1.6v12H3z"/></svg>',
  fwd: '<svg viewBox="0 0 16 16"><path d="M5 2.5v11L12 8zM11.4 2H13v12h-1.6z"/></svg>',
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const statusClass = (s) => "s-" + s.replace(/\s+/g, "-");
const instances = new WeakMap();

const TEMPLATE = `
<div class="map" id="map"></div>
<section class="ov panel queue" aria-label="Dispatch queue">
  <div class="q-head"><div class="q-title">Dispatch queue</div><div class="q-sub" id="q-sub"></div><div class="stats" id="stats"></div></div>
  <div class="list" id="list"></div>
</section>
<section class="ov panel ctl" aria-label="Map controls">
  <div class="seg" id="bm" role="group" aria-label="Basemap"></div>
  <div class="chips" id="chips" role="group" aria-label="Map layers"></div>
  <div class="tools"><button class="ghost" id="reset" type="button">Reset view</button><button class="ghost" id="t3d" type="button" aria-pressed="false">3D terrain</button></div>
  <details><summary>Legend</summary><div class="legend">
    <div><span class="dot" style="background:var(--ok)"></span>Assigned, number is priority rank</div>
    <div><span class="dot" style="background:var(--warn)"></span>Waiting or arriving late</div>
    <div><span class="dot" style="background:var(--bad)"></span>Cut off, no road in</div>
    <div><span class="sw" style="border-color:var(--boat)"></span>Boat route</div>
    <div><span class="sw" style="border-color:var(--medical)"></span>Medical route</div>
    <div><span class="sw" style="border-color:var(--ground)"></span>Ground route</div>
    <div><span class="sw dash" style="border-color:#ffb224"></span>Road degraded</div>
    <div><span class="sw dash" style="border-color:#ff4d4f"></span>Road closed</div>
    <div><span class="dot" style="background:#3a9bea;opacity:.6"></span>Flood extent, darker is worse</div>
  </div></details>
</section>
<section class="ov panel dock" aria-label="Simulation time">
  <div class="btns"><button class="ib" id="back" type="button" aria-label="Back 6 hours"></button><button class="ib play" id="play" type="button" aria-label="Play"></button><button class="ib" id="fwd" type="button" aria-label="Forward 6 hours"></button></div>
  <div class="track" id="track" tabindex="0" role="slider" aria-label="Hours since the flood wave reached Tinsukia" aria-valuemin="0" aria-valuemax="144">
    <div class="cap">Towns at high or extreme hazard</div>
    <svg viewBox="0 0 720 100" preserveAspectRatio="none" aria-hidden="true"><defs><clipPath id="past"><rect id="clip-past" x="0" y="0" width="0" height="100"/></clipPath></defs>
      <path id="area-all" fill="currentColor" opacity=".16"/><path id="area-past" fill="currentColor" opacity=".5" clip-path="url(#past)"/><path id="line" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>
    <div class="thumb" id="thumb"></div><div class="ticks" id="ticks"></div>
  </div>
  <div class="read"><b id="r-h"></b><span id="r-d"></span></div>
</section>
<div class="tip" id="tip"></div>`;

function create(root, ctx) {
  const wrap = root.querySelector("#root");
  wrap.className = "console"; wrap.innerHTML = TEMPLATE;
  const $ = (id) => wrap.querySelector("#" + id);
  const inst = {
    ctx, data: null, hour: null, selected: null, playing: false, pending: false, dragging: false, ready: false,
    basemap: "sat", layers: new Set(LAYER_CHIPS.map((c) => c[0])), terrain: false, fitted: false,
    markers: { inc: new Map(), team: new Map(), town: new Map() }, timer: null, raf: 0, lastCommit: 0,
  };
  const tip = $("tip");
  const showTip = (html, el) => {
    tip.innerHTML = html;
    const w = wrap.getBoundingClientRect(), r = el.getBoundingClientRect();
    tip.classList.add("on");
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(w.width - tw - 8, r.left - w.left + r.width / 2 - tw / 2)) + "px";
    tip.style.top = (r.top - w.top - th - 8 < 8 ? r.bottom - w.top + 8 : r.top - w.top - th - 8) + "px";
  };
  const hideTip = () => tip.classList.remove("on");

  // ---- map ----
  const style = {
    version: 8, sources: SOURCES,
    layers: [{ id: "bg", type: "background", paint: { "background-color": "#0d1a22" } },
      ...["imagery", "places", "topo", "streets", "dark", "darklabels"].map((id) => ({ id: "base-" + id, type: "raster", source: id, layout: { visibility: "none" } })),
      { id: "hillshade", type: "hillshade", source: "dem", layout: { visibility: "none" }, paint: { "hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#1a2730", "hillshade-highlight-color": "#ffffff" } }],
  };
  const map = new maplibregl.Map({ container: $("map"), style, center: [92.65, 26.7], zoom: 6.4, minZoom: 4, maxZoom: 17, attributionControl: false, pitchWithRotate: true, dragRotate: true });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
  inst.map = map;

  const padding = () => ({ left: (wrap.querySelector(".queue").offsetWidth || 328) + 30, right: 40, top: 200, bottom: 130 });
  const fit = (animate) => map.fitBounds([[89.7, 25.7], [95.7, 27.9]], { padding: padding(), duration: animate ? 800 : 0, maxZoom: 9 });

  const setBasemap = (id) => {
    inst.basemap = id;
    const bm = BASEMAPS.find((b) => b.id === id);
    ["imagery", "places", "topo", "streets", "dark", "darklabels"].forEach((l) => map.setLayoutProperty("base-" + l, "visibility", bm.layers.includes(l) ? "visible" : "none"));
    map.setLayoutProperty("hillshade", "visibility", bm.hill || inst.terrain ? "visible" : "none");
    $("bm").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  };
  const setTerrain = (on) => {
    inst.terrain = on;
    map.setTerrain(on ? { source: "dem", exaggeration: 1.7 } : null);
    map.easeTo({ pitch: on ? 55 : 0, duration: 800 });
    $("t3d").setAttribute("aria-pressed", String(on));
    setBasemap(inst.basemap);
  };
  const applyLayerVis = () => {
    const on = inst.layers;
    const vis = (ids, k) => ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on.has(k) ? "visible" : "none"));
    vis(["flood"], "flood"); vis(["roads-casing", "roads-open", "roads-degraded", "roads-blocked"], "roads"); vis(["routes-casing", "routes", "routes-flow"], "routes");
    wrap.classList.toggle("show-names", on.has("towns")); wrap.classList.toggle("hide-team", !on.has("teams")); wrap.classList.toggle("hide-inc", !on.has("inc"));
    chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(on.has(b.dataset.k))));
  };

  // ---- static controls ----
  $("bm").innerHTML = BASEMAPS.map((b) => `<button type="button" data-id="${b.id}" aria-pressed="false">${b.label}</button>`).join("");
  $("bm").onclick = (e) => { const b = e.target.closest("button"); if (b && inst.ready) setBasemap(b.dataset.id); };
  const chips = $("chips");
  chips.innerHTML = LAYER_CHIPS.map(([k, l]) => `<button class="chip" type="button" data-k="${k}" aria-pressed="true">${l}</button>`).join("");
  chips.onclick = (e) => { const b = e.target.closest("button"); if (!b || !inst.ready) return; inst.layers.has(b.dataset.k) ? inst.layers.delete(b.dataset.k) : inst.layers.add(b.dataset.k); applyLayerVis(); };
  $("reset").onclick = () => { if (inst.terrain) setTerrain(false); map.easeTo({ bearing: 0, pitch: 0, duration: 400 }); fit(true); };
  $("t3d").onclick = () => inst.ready && setTerrain(!inst.terrain);
  $("back").innerHTML = ICON.back; $("fwd").innerHTML = ICON.fwd; $("play").innerHTML = ICON.play;

  // ---- time dock ----
  const track = $("track");
  const maxH = () => inst.data.maxHour;
  const hourFromEvent = (e) => {
    const r = track.getBoundingClientRect();
    const h = Math.round(((e.clientX - r.left) / r.width) * maxH() / inst.data.step) * inst.data.step;
    return Math.max(0, Math.min(maxH(), h));
  };
  const commitHour = (h, force) => {
    if (h === inst.hour && !force) return;
    inst.hour = h; paintTime(); inst.pending = true; inst.ctx.setStateValue("hour", h);
  };
  const setPlaying = (on) => {
    inst.playing = on; $("play").innerHTML = on ? ICON.pause : ICON.play; $("play").setAttribute("aria-label", on ? "Pause" : "Play");
    clearInterval(inst.timer);
    if (on) inst.timer = setInterval(() => {
      if (inst.pending) return;
      if (inst.hour >= maxH()) return setPlaying(false);
      commitHour(Math.min(maxH(), inst.hour + inst.data.step));
    }, 1100);
  };
  $("play").onclick = () => { if (!inst.data) return; if (!inst.playing && inst.hour >= maxH()) commitHour(0); setPlaying(!inst.playing); };
  $("back").onclick = () => { setPlaying(false); commitHour(Math.max(0, inst.hour - inst.data.step)); };
  $("fwd").onclick = () => { setPlaying(false); commitHour(Math.min(maxH(), inst.hour + inst.data.step)); };
  track.onpointerdown = (e) => { setPlaying(false); inst.dragging = true; track.setPointerCapture(e.pointerId); const h = hourFromEvent(e); inst.hour = h; paintTime(); commitHour(h, true); };
  track.onpointermove = (e) => {
    if (!inst.dragging) return;
    const h = hourFromEvent(e); if (h === inst.hour) return;
    inst.hour = h; paintTime();
    const now = performance.now(); if (now - inst.lastCommit > 160) { inst.lastCommit = now; commitHour(h, true); }
  };
  track.onpointerup = (e) => { if (!inst.dragging) return; inst.dragging = false; commitHour(hourFromEvent(e), true); };
  track.onkeydown = (e) => {
    const s = inst.data.step;
    if (e.key === "ArrowLeft") { commitHour(Math.max(0, inst.hour - s)); e.preventDefault(); }
    if (e.key === "ArrowRight") { commitHour(Math.min(maxH(), inst.hour + s)); e.preventDefault(); }
  };
  function paintTime() {
    const d = inst.data; if (!d) return;
    const x = (inst.hour / d.maxHour) * 100;
    $("thumb").style.left = x + "%"; $("clip-past").setAttribute("width", String((inst.hour / d.maxHour) * 720));
    $("r-h").textContent = "+" + inst.hour + " h";
    $("r-d").textContent = "Day " + (Math.floor(inst.hour / 24) + 1) + ", " + String(inst.hour % 24).padStart(2, "0") + ":00";
    track.setAttribute("aria-valuenow", String(inst.hour)); track.setAttribute("aria-valuetext", $("r-h").textContent + ", " + $("r-d").textContent);
  }
  function paintSeries() {
    const s = inst.data.series, mx = Math.max(1, ...s.map((p) => p.n));
    const pts = s.map((p) => [(p.h / inst.data.maxHour) * 720, 98 - (p.n / mx) * 74]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    $("line").setAttribute("d", line);
    const area = line + ` L720 100 L0 100 Z`;
    $("area-all").setAttribute("d", area); $("area-past").setAttribute("d", area);
    const days = Math.floor(inst.data.maxHour / 24);
    $("ticks").innerHTML = Array.from({ length: days + 1 }, (_, i) => `<span style="left:${((i * 24) / inst.data.maxHour) * 100}%">${i === 0 ? "Day 1" : "+" + i * 24 + " h"}</span>`).join("");
  }

  // ---- queue ----
  const list = $("list");
  function paintQueue() {
    const d = inst.data, top = list.scrollTop;
    $("q-sub").textContent = d.kpi.reports ? `${d.kpi.reports} reports ranked by priority P = S + D x S` : "No reports loaded";
    $("stats").innerHTML = [[d.kpi.reports, "Reports"], [d.kpi.high, "High severity"], [d.kpi.dispatched, "Dispatched"], [d.kpi.waiting, "Not sent"]].map(([n, l]) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("");
    if (!d.incidents.length) { list.innerHTML = '<div class="empty">No incidents to show. Load the Assam scenario or add a report in the Incident reports tab below.</div>'; return; }
    const mx = Math.max(...d.incidents.map((i) => i.P));
    list.innerHTML = d.incidents.map((i) => {
      const sel = i.tag === inst.selected;
      const detail = sel ? `<div class="detail"><p class="quote">&ldquo;${esc(i.message)}&rdquo;</p>
        <div class="figs"><div class="fig"><b>${i.S}</b><span>Severity, ${esc(i.sLabel)}</span></div><div class="fig"><b>${i.D}</b><span>Delay, ${esc(i.dLabel)}</span></div><div class="fig"><b>${i.P}</b><span>Priority</span></div></div>
        <div class="dispatch">${i.team ? `<span class="k">Team</span> ${esc(i.team)} (${esc(i.teamType)}), ETA ${i.eta} h<br><span class="k">Route</span> ${esc(i.route)}` : `<span class="k">No team sent.</span> ${i.status === "cut off" ? "Floodwater has closed every road or ferry into town." : "Waiting for a free, suitable team."}`}</div></div>` : "";
      return `<button class="row ${sel ? "sel" : ""}" type="button" data-tag="${esc(i.tag)}" aria-expanded="${sel}"><div class="r-main"><span class="badge ${statusClass(i.status)}">${i.rank}</span>
        <div><div class="r-name">${esc(i.zone)}<small>${esc(i.tag)}</small></div><div class="r-meta">${esc(i.statusLabel)}${i.team ? " &middot; " + esc(i.team) + ", " + i.eta + " h" : ""}</div></div>
        <div class="r-p">${i.P}<i style="--w:${Math.round((i.P / mx) * 100)}%"></i></div></div>${detail}</button>`;
    }).join("");
    list.scrollTop = top;
  }
  list.onclick = (e) => { const b = e.target.closest(".row"); if (b) select(b.dataset.tag, { fly: true, emit: true }); };

  // ---- markers ----
  function syncMarkers(store, items, key, make, update, anchor) {
    const seen = new Set();
    for (const it of items) {
      const k = key(it); seen.add(k);
      let m = store.get(k);
      if (!m) { const el = make(it); m = { el, mk: new maplibregl.Marker({ element: el, anchor }).setLngLat([it.lon, it.lat]).addTo(map) }; store.set(k, m); }
      else m.mk.setLngLat([it.lon, it.lat]);
      update(m.el, it);
    }
    for (const [k, m] of store) if (!seen.has(k)) { m.mk.remove(); store.delete(k); }
  }
  const bindTip = (el, getHtml) => { el.onmouseenter = () => showTip(getHtml(), el); el.onmouseleave = hideTip; };
  function paintMarkers() {
    const d = inst.data;
    syncMarkers(inst.markers.town, d.towns, (t) => t.name, (t) => {
      const el = document.createElement("div"); el.className = "mk"; el.innerHTML = '<div class="twn"><i></i><b></b></div>'; el.style.zIndex = 1; return el;
    }, (el, t) => {
      el.querySelector("i").style.background = HAZ_COLOR[t.hazard]; el.querySelector("b").textContent = t.name;
      el.dataset.name = t.name;
      el.onmouseenter = () => showTip(`<b>${esc(t.name)}</b><br><em>Hazard</em> ${esc(t.hazard.toLowerCase())}, water ${esc(t.rise.toLowerCase())}<br><em>Open roads</em> ${t.open}<br>${esc(t.leadText)}`, el.querySelector("i"));
      el.onmouseleave = hideTip;
    }, "center");
    syncMarkers(inst.markers.team, d.teams, (t) => t.id, () => { const el = document.createElement("div"); el.className = "mk tm-wrap"; el.innerHTML = '<div class="tm"></div>'; el.style.zIndex = 2; return el; },
      (el, t) => {
        const c = el.firstChild; c.className = "tm " + t.type + (t.free ? "" : " off"); c.textContent = t.id;
        bindTip(el, () => `<b>${esc(t.id)}, ${esc(t.type)} team</b><br><em>Base</em> ${esc(t.base)}, capacity ${t.capacity}<br>${t.assigned ? "Assigned to " + esc(t.assigned) : t.free ? "Free" : "Unavailable"}`);
      }, "center");
    syncMarkers(inst.markers.inc, d.incidents, (i) => i.tag, () => { const el = document.createElement("div"); el.className = "mk mk-inc"; el.innerHTML = '<div class="inc"></div>'; el.style.zIndex = 4; return el; },
      (el, i) => {
        const c = el.firstChild; c.className = "inc " + statusClass(i.status); c.textContent = i.rank; el.classList.toggle("sel", i.tag === inst.selected);
        el.setAttribute("role", "button"); el.setAttribute("aria-label", `Rank ${i.rank}, ${i.zone}, ${i.statusLabel}`);
        bindTip(el, () => `<b>#${i.rank} ${esc(i.tag)}, ${esc(i.zone)}</b><br><em>Priority</em> ${i.P} &middot; ${esc(i.statusLabel)}${i.team ? "<br><em>Team</em> " + esc(i.team) + ", " + i.eta + " h" : ""}`);
        el.onclick = (ev) => { ev.stopPropagation(); select(i.tag, { fly: false, emit: true }); };
      }, "center");
    for (const [name, m] of inst.markers.town) m.el.firstChild.classList.toggle("pin", false);
    const sel = d.incidents.find((i) => i.tag === inst.selected);
    if (sel) inst.markers.town.get(sel.zone)?.el.firstChild.classList.add("pin");
  }

  // ---- selection ----
  function select(tag, { fly, emit }) {
    inst.selected = tag;
    if (inst.data) { paintQueue(); paintMarkers(); }
    const i = inst.data && inst.data.incidents.find((x) => x.tag === tag);
    if (fly && i) map.flyTo({ center: [i.lon, i.lat], zoom: Math.max(map.getZoom(), 7.8), duration: 800, padding: padding() });
    list.querySelector(".row.sel")?.scrollIntoView({ block: "nearest" });
    if (emit) inst.ctx.setStateValue("selected", tag);
  }

  // ---- overlay layers ----
  const fc = (features) => ({ type: "FeatureCollection", features });
  const feat = (geometry, properties) => ({ type: "Feature", geometry, properties });
  function paintOverlays() {
    const d = inst.data;
    map.getSource("flood").setData(fc(d.towns.filter((t) => HAZ_KM[t.hazard] > 0).map((t) =>
      feat({ type: "Point", coordinates: [t.lon, t.lat] }, { haz: t.hazard, r0: (HAZ_KM[t.hazard] * 1000) / (156543.03 * Math.cos((t.lat * Math.PI) / 180)) }))));
    map.getSource("roads").setData(fc(d.roads.map((r) => feat({ type: "LineString", coordinates: [r.a, r.b] }, { status: r.status, label: r.label, kind: r.kind, km: r.km }))));
    map.getSource("routes").setData(fc(d.routes.map((r) => feat({ type: "LineString", coordinates: r.path }, { team: r.team, type: r.type, sel: r.tag === inst.selected ? 1 : 0, tag: r.tag }))));
  }
  function addOverlays() {
    ["flood", "roads", "routes"].forEach((id) => map.addSource(id, { type: "geojson", data: fc([]) }));
    const line = { "line-cap": "round", "line-join": "round" };
    map.addLayer({ id: "flood", type: "circle", source: "flood", paint: {
      "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 0, ["get", "r0"], 6, ["max", ["*", ["get", "r0"], 64], 16], 24, ["*", ["get", "r0"], 16777216]],
      "circle-color": ["match", ["get", "haz"], "Extreme", HAZ_COLOR.Extreme, "High", HAZ_COLOR.High, HAZ_COLOR.Moderate],
      "circle-opacity": 0.5, "circle-blur": 0.35 } });
    map.addLayer({ id: "roads-casing", type: "line", source: "roads", layout: line, paint: { "line-color": "#06121a", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 5, 3, 10, 6] } });
    map.addLayer({ id: "roads-open", type: "line", source: "roads", filter: ["==", ["get", "status"], "open"], layout: line, paint: { "line-color": "#f4f7fa", "line-opacity": 0.85, "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1.4, 10, 3] } });
    map.addLayer({ id: "roads-degraded", type: "line", source: "roads", filter: ["==", ["get", "status"], "degraded"], layout: { "line-join": "round" }, paint: { "line-color": "#ffb224", "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 10, 4], "line-dasharray": [2, 1.4] } });
    map.addLayer({ id: "roads-blocked", type: "line", source: "roads", filter: ["==", ["get", "status"], "blocked"], layout: { "line-join": "round" }, paint: { "line-color": "#ff4d4f", "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2.2, 10, 4.4], "line-dasharray": [1, 1.6] } });
    const rc = ["match", ["get", "type"], "boat", TEAM_COLOR.boat, "medical", TEAM_COLOR.medical, TEAM_COLOR.ground];
    const rw = (a, b) => ["interpolate", ["linear"], ["zoom"], 5, ["+", a, ["*", 1.5, ["get", "sel"]]], 10, ["+", b, ["*", 2, ["get", "sel"]]]];
    map.addLayer({ id: "routes-casing", type: "line", source: "routes", layout: line, paint: { "line-color": "#06121a", "line-opacity": 0.7, "line-width": ["+", 3, rw(3, 5)] } });
    map.addLayer({ id: "routes", type: "line", source: "routes", layout: line, paint: { "line-color": rc, "line-width": rw(3, 5) } });
    map.addLayer({ id: "routes-flow", type: "line", source: "routes", layout: line, paint: { "line-color": "#ffffff", "line-opacity": 0.8, "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1, 10, 2], "line-dasharray": DASH_FRAMES[0] } });
    for (const id of ["roads-open", "roads-degraded", "roads-blocked"]) {
      map.on("mousemove", id, (e) => {
        const p = e.features[0].properties; map.getCanvas().style.cursor = "help";
        tip.innerHTML = `<b>${esc(p.label)}</b><br><em>${esc(p.kind)}, ${p.km} km</em><br>Status: ${esc(p.status)}`; tip.classList.add("on");
        const w = wrap.getBoundingClientRect(); tip.style.left = Math.min(w.width - 250, e.point.x + 14) + "px"; tip.style.top = e.point.y + 14 + "px";
      });
      map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; hideTip(); });
    }
  }
  let frame = 0, lastTick = 0;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const animate = (t) => {
    inst.raf = requestAnimationFrame(animate);
    if (reduce || !inst.ready || !inst.layers.has("routes") || t - lastTick < 90) return;
    lastTick = t; frame = (frame + 1) % DASH_FRAMES.length; map.setPaintProperty("routes-flow", "line-dasharray", DASH_FRAMES[frame]);
  };

  map.on("load", () => {
    addOverlays(); inst.ready = true; setBasemap(inst.basemap); applyLayerVis(); fit(false);
    if (inst.data) inst.apply();
    inst.raf = requestAnimationFrame(animate);
  });
  const zoomClass = () => wrap.classList.toggle("zoomed", map.getZoom() >= 7.2);
  map.on("zoom", zoomClass); zoomClass();
  map.on("error", (e) => console.warn("map:", e && e.error && e.error.message));
  map.on("click", (e) => { if (!e.originalEvent.defaultPrevented) hideTip(); });

  inst.apply = () => {
    if (!inst.ready || !inst.data) return;
    paintOverlays(); paintMarkers(); paintQueue();
  };
  inst.update = (data) => {
    inst.data = data;
    wrap.style.height = data.height + "px";
    if (inst.hour === data.hour) inst.pending = false;
    else if (!inst.dragging && !inst.pending) inst.hour = data.hour;
    if (data.selected !== inst.selected && data.selected) inst.selected = data.selected;
    paintSeries(); paintTime(); map.resize(); inst.apply();
  };
  inst.destroy = () => { clearInterval(inst.timer); cancelAnimationFrame(inst.raf); map.remove(); };
  return inst;
}

export default function (component) {
  const { parentElement, data, setStateValue } = component;
  let inst = instances.get(parentElement);
  if (!inst) { inst = create(parentElement, { setStateValue }); instances.set(parentElement, inst); }
  inst.ctx.setStateValue = setStateValue;
  inst.update(data);
  return () => { inst.destroy(); instances.delete(parentElement); };
}
