"""The operations console: a MapLibre map with floating panels, mounted as a Streamlit custom component (v2).

Python builds a plain-data payload from the engine's results; the JavaScript in static/console.js draws it.
The map object lives in the browser and is only updated, never recreated, so pan, zoom and basemap survive reruns.
"""
from pathlib import Path

import streamlit as st

import data as D
import engine as E

HERE = Path(__file__).parent / "static"
MAX_HOUR, STEP, HEIGHT = 144, 6, 760
_CONSOLE = st.components.v2.component(
    "operations_console",
    js=(HERE / "console.js").read_text(encoding="utf-8"),
    css=(HERE / "console.css").read_text(encoding="utf-8"),
    html='<div id="root"></div>',
)


def status_label(e):
    return "assigned late" if e["status"] == "assigned" and not e["in_time"] else e["status"]


def _fan(town, k, scale):
    """First marker sits on the town; any others fan out around it."""
    lat, lon = D.COORDS[town]
    if k == 0:
        return lon, lat
    return lon + scale * ((k - 1) % 3 - 1 + 0.5), lat + scale * ((k - 1) // 3 + 1)


def payload(hour, res, teams, selected):
    ranked, status = res["ranked"], res["road_status"]
    towns = []
    for name, (lat, lon) in D.COORDS.items():
        hz, rise = E.zone_phase(name, hour)
        rec = E.zone_record(name, hour, status)
        lead = "Already flooded" if rec["lead_hours"] == 0 else f"Wave arrives in {rec['lead_hours']:g} h"
        towns.append(dict(name=name, lat=lat, lon=lon, hazard=hz, rise=rise, open=rec["open_routes"], leadText=lead))
    roads = [dict(id=rid, label=e["label"], kind=e["kind"], km=e["km"], status=status[rid],
                  a=[D.COORDS[e["a"]][1], D.COORDS[e["a"]][0]], b=[D.COORDS[e["b"]][1], D.COORDS[e["b"]][0]]) for rid, e in D.EDGES.items()]
    team_by_id = {t["id"]: t for t in teams}
    routes = [dict(tag=e["tag"], team=e["team"], type=team_by_id[e["team"]]["type"],
                   path=[[D.COORDS[n][1], D.COORDS[n][0]] for n in e["route"]["path"]]) for e in ranked if e["route"]]
    seen, busy = {}, {e["team"]: e for e in ranked if e["team"]}
    team_rows = []
    for t in teams:
        k = seen[t["base"]] = seen.get(t["base"], 0) + 1
        lon, lat = D.COORDS[t["base"]][1] + 0.1 + 0.07 * (k - 1), D.COORDS[t["base"]][0] - 0.09
        a = busy.get(t["id"])
        team_rows.append(dict(id=t["id"], type=t["type"], base=t["base"], capacity=t["capacity"], free=bool(t["available"]),
                              lon=lon, lat=lat, assigned=f"{a['tag']} {a['zone']}" if a else None))
    incidents = []
    for e in ranked:
        k = sum(1 for x in ranked if x["zone"] == e["zone"] and x["rank"] < e["rank"])
        lon, lat = _fan(e["zone"], k, 0.09)
        incidents.append(dict(
            tag=e["tag"], rank=e["rank"], zone=e["zone"], lon=lon, lat=lat, S=e["S"], D=e["D"], P=e["P"],
            sLabel=e["s_label"].lower(), dLabel=e["d_label"].lower(), status=e["status"], statusLabel=status_label(e).capitalize(),
            team=e["team"], teamType=team_by_id[e["team"]]["type"] if e["team"] else None,
            eta=round(e["route"]["hours"], 1) if e["route"] else None, route=" > ".join(e["route"]["path"]) if e["route"] else "",
            message=e["message"]))
    series = [dict(h=h, n=sum(E.zone_phase(n, h)[0] in ("High", "Extreme") for n in D.COORDS)) for h in range(0, MAX_HOUR + 1, 3)]
    n_ok = sum(e["status"] == "assigned" for e in ranked)
    return dict(hour=hour, maxHour=MAX_HOUR, step=STEP, height=HEIGHT, selected=selected, series=series, towns=towns, roads=roads,
                routes=routes, teams=team_rows, incidents=incidents,
                kpi=dict(reports=len(ranked), high=sum(e["s_label"] == "HIGH" for e in ranked), dispatched=n_ok, waiting=len(ranked) - n_ok))


def console_state(key="console"):
    """Hour and selection chosen in the browser (last values), read before the analysis runs."""
    s = st.session_state.get(key) or {}
    return int(s.get("hour", 36)), s.get("selected")


def show(data, key="console"):
    return _CONSOLE(key=key, data=data, height=HEIGHT, on_hour_change=lambda: None, on_selected_change=lambda: None)
