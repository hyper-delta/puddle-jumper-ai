"""Pipeline engine: message -> NLP -> severity -> delay risk -> priority -> CSP -> A* -> dispatch.

No printing and no GUI code here. Every function returns plain data so the app can
show each step and the tests can check the numbers.
"""
import heapq
import math
import re
from functools import cmp_to_key

from data import (ALIASES, ARRIVAL, COORDS, EDGES, EQUIPMENT_NEEDED, VMAX, haversine)

TIE_BAND = 0.5

# ---------------------------------------------------------------- Step 1: NLP
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}

KEYWORDS = {
    "trapped":      ["trapped", "stuck", "cannot get out", "can't get out"],
    "elderly":      ["elderly", "grandmother", "grandfather", "grandma", "grandpa", "old man", "old woman", "old person"],
    "child":        ["child", "children", "baby", "kid", "kids"],
    "disabled":     ["disabled", "cannot walk", "can't walk", "immobile", "wheelchair"],
    "medical":      ["serious injury", "serious medical", "medical emergency", "critical patient", "severe injury",
                     "unconscious", "bleeding"],
    "water_fast":   ["rising fast", "rising quickly", "rising rapidly", "fast rising", "rapidly rising"],
    "water_rise":   ["water is rising", "water rising", "rising"],
    "road_blocked": ["road is completely blocked", "road completely blocked", "road is blocked", "road blocked",
                     "roads closed", "road closed", "road is closed", "completely blocked", "blocked road"],
    "road_partial": ["partially flooded", "partly flooded", "road damaged", "road is damaged", "road flooded",
                     "road is flooded"],
    "comms":        ["battery", "no signal", "weak signal", "poor signal", "no network", "network is down",
                     "phone is dying", "phone dying", "phone is dead", "phone not working", "cannot communicate",
                     "can't communicate", "communication lost"],
    "evac":         ["evacuate immediately", "immediate evacuation", "need evacuation", "evacuate now",
                     "rescue us immediately"],
}
FIELD_LABELS = [("zone", "Zone"), ("people", "People count"), ("trapped", "Trapped / stuck"),
                ("elderly", "Elderly present"), ("child", "Child present"), ("disabled", "Disabled / immobile"),
                ("medical", "Serious medical"), ("water_fast", "Water rising fast"), ("water_rise", "Water rising"),
                ("road_blocked", "Road completely blocked"), ("road_partial", "Road partially flooded"),
                ("comms", "Phone dying / no signal"), ("evac", "Immediate evacuation")]


def _find(text, phrases):
    for p in phrases:
        if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text):
            return p
    return None


def extract_fields(message):
    text = message.lower()
    f, ev = {}, {}
    hits = [(text.find(a), a) for a in ALIASES if re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", text)]
    if hits:
        _, alias = min(hits)
        f["zone"], ev["zone"] = ALIASES[alias], alias
    else:
        f["zone"], ev["zone"] = None, None
    m = re.search(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(?:people|persons|person|members|of us)\b", text)
    if m:
        tok = m.group(1)
        f["people"] = int(tok) if tok.isdigit() else NUMBER_WORDS[tok]
        ev["people"] = m.group(0)
    else:
        f["people"], ev["people"] = 1, "not stated, assume 1"
    for key, words in KEYWORDS.items():
        hit = _find(text, words)
        f[key], ev[key] = hit is not None, hit
    return f, ev


# ------------------------------------------------------------ Step 2: severity
def group_points(n):
    return 3 if n >= 11 else 2 if n >= 7 else 1 if n >= 4 else 0


def score_severity(f):
    rows = []

    def add(rule, meaning, pts, counted=True, note=""):
        rows.append(dict(rule=rule, meaning=meaning, points=pts, counted=counted, note=note))

    if f["trapped"]:  add("R1", "Trapped or stuck", 3)
    if f["elderly"]:  add("R2", "Elderly person present", 2)
    if f["child"]:    add("R3", "Child present", 2)
    if f["disabled"]: add("R4", "Disabled / immobile person", 2)
    if f["medical"]:  add("R5", "Serious medical emergency", 4)
    if f["water_fast"]:
        add("R6", "Water rising fast", 2)
        if f["water_rise"]:
            add("R7", "Water rising", 1, False, "ignored: R6 is the stronger rule")
    elif f["water_rise"]:
        add("R7", "Water rising", 1)
    if f["road_blocked"]:
        add("R8", "Road completely blocked", 2)
        if f["road_partial"]:
            add("R9", "Road partially flooded", 1, False, "ignored: R8 is the stronger rule")
    elif f["road_partial"]:
        add("R9", "Road partially flooded", 1)
    gp = group_points(f["people"])
    if gp:         add("R10", f"Group of {f['people']} people", gp)
    if f["comms"]: add("R11", "Communication at risk", 1)
    if f["evac"]:  add("R12", "Immediate evacuation needed", 3)
    rows.sort(key=lambda r: int(r["rule"][1:]))
    score = sum(r["points"] for r in rows if r["counted"])
    label = "LOW" if score <= 2 else "MEDIUM" if score <= 5 else "HIGH"
    return rows, score, label


# --------------------------------------------- flood simulation and road status
def zone_phase(zone, hour):
    """Hazard and rise rate for a zone, from where the flood wave is relative to it."""
    dt = hour - ARRIVAL[zone]
    if dt < -48:  return "Low", "Stable"
    if dt < -12:  return "Moderate", "Slow"
    if dt < 0:    return "High", "Fast"
    if dt < 36:   return "Extreme", "Fast"
    if dt < 72:   return "Extreme", "Slow"
    if dt < 120:  return "High", "Stable"
    return "Moderate", "Stable"


def edge_status(e, hour, manual_blocked=(), auto_cut=True):
    """'open', 'degraded' (slow, x2.5 time) or 'blocked'."""
    if e["id"] in manual_blocked:
        return "blocked"
    if not auto_cut or e["kind"] not in ("low", "ferry"):
        return "open"
    dts = [hour - ARRIVAL[e["a"]], hour - ARRIVAL[e["b"]]]
    if e["kind"] == "ferry":
        return "blocked" if any(0 <= d < 36 for d in dts) else "open"
    if any(12 <= d < 48 for d in dts):
        return "blocked"
    if any(0 <= d < 72 for d in dts):
        return "degraded"
    return "open"


def road_network(hour, manual_blocked=(), auto_cut=True):
    """Adjacency list of usable roads plus the status of every road."""
    status = {rid: edge_status(e, hour, manual_blocked, auto_cut) for rid, e in EDGES.items()}
    graph = {n: [] for n in COORDS}
    for rid, e in EDGES.items():
        if status[rid] == "blocked":
            continue
        t = e["hours"] * (2.5 if status[rid] == "degraded" else 1.0)
        graph[e["a"]].append((e["b"], t, rid))
        graph[e["b"]].append((e["a"], t, rid))
    return graph, status


# --------------------------------------------------------- Step 3: delay risk
HAZARD_PTS = {"Low": 0, "Moderate": 1, "High": 2, "Extreme": 3}
RISE_PTS = {"Stable": 0, "Slow": 1, "Fast": 2}


def zone_record(zone, hour, status):
    """What the 'sensors' say about a zone right now. open_routes and exposed come from the road network."""
    hazard, rise = zone_phase(zone, hour)
    open_roads = [e for rid, e in EDGES.items() if status[rid] != "blocked" and zone in (e["a"], e["b"])]
    return dict(hazard=hazard, rise=rise, open_routes=len(open_roads),
                exposed=all(e["exposed"] for e in open_roads),     # True when no safe road is left (or no road at all)
                lead_hours=max(0.0, ARRIVAL[zone] - hour))


def score_delay_risk(z):
    o = 0 if z["open_routes"] >= 3 else 1 if z["open_routes"] == 2 else 3
    lead = z["lead_hours"]
    l = 0 if lead > 6 else 1 if lead >= 2 else 3
    rows = [
        dict(factor="H", meaning="Hazard level", reading=z["hazard"], points=HAZARD_PTS[z["hazard"]]),
        dict(factor="R", meaning="Water rise rate", reading=z["rise"], points=RISE_PTS[z["rise"]]),
        dict(factor="O", meaning="Open routes", reading=f"{z['open_routes']} route(s)", points=o),
        dict(factor="X", meaning="Exposed path (no safe road left)", reading="Yes" if z["exposed"] else "No",
             points=2 if z["exposed"] else 0),
        dict(factor="L", meaning="Lead time", reading=("already flooded" if lead == 0 else f"{lead:g} h"), points=l),
    ]
    drs = sum(r["points"] for r in rows)
    label, d = ("LOW", 0.1) if drs <= 3 else ("MEDIUM", 0.3) if drs <= 7 else ("HIGH", 0.6)
    return rows, drs, label, d


# ------------------------------------------------- Step 4: priority and ranking
def priority(s, d):
    return round(s + d * s, 2)


def rank_emergencies(ems):
    def before(a, b):
        if abs(a["P"] - b["P"]) <= TIE_BAND:
            ka, kb = (a["S"], a["DRS"], -a["idx"]), (b["S"], b["DRS"], -b["idx"])
            return -1 if ka > kb else 1 if ka < kb else 0
        return -1 if a["P"] > b["P"] else 1
    return sorted(ems, key=cmp_to_key(before))


# ------------------------------------------------------------------ Step 6: A*
def a_star(graph, start, goal):
    """Returns (path, hours, trace). Heuristic = straight-line km / fastest speed (never overestimates)."""
    h = lambda n: haversine(COORDS[n], COORDS[goal]) / VMAX
    open_list, best_g, closed, trace = [(h(start), 0.0, start, [start])], {start: 0.0}, set(), []
    while open_list:
        f, g, node, path = heapq.heappop(open_list)
        if node in closed:
            continue
        closed.add(node)
        trace.append(dict(node=node, g=round(g, 2), h=round(h(node), 2), f=round(f, 2)))
        if node == goal:
            return path, g, trace
        for nb, t, _ in graph[node]:
            if g + t < best_g.get(nb, math.inf):
                best_g[nb] = g + t
                heapq.heappush(open_list, (g + t + h(nb), g + t, nb, path + [nb]))
    return None, math.inf, trace


# ------------------------------------------------------------------ Step 5: CSP
def required_team_type(f):
    if f["medical"]:
        return "medical"
    if f["trapped"] and (f["water_fast"] or f["water_rise"]):
        return "boat"
    return "ground"


def check_team(em, team, taken):
    """Constraints C1..C5 in order. Returns (cells, feasible); a failed cell stops the check."""
    names = ["C1 free", "C2 capability", "C3 equipment", "C4 capacity", "C5 medical"]
    cells = {}
    checks = [
        (lambda: (team["available"] and team["id"] not in taken),
         lambda: "FAIL (busy)" if not team["available"] else f"FAIL (given to {taken[team['id']]})",
         lambda: "pass"),
        (lambda: team["type"] == em["need_type"],
         lambda: f"FAIL ({team['type']} team)", lambda: f"pass ({team['type']})"),
        (lambda: not (EQUIPMENT_NEEDED[em["need_type"]] - team["equipment"]),
         lambda: "FAIL (no " + ", ".join(sorted(EQUIPMENT_NEEDED[em["need_type"]] - team["equipment"])) + ")",
         lambda: "pass"),
        (lambda: team["capacity"] >= em["people"],
         lambda: f"FAIL ({team['capacity']} < {em['people']})", lambda: f"pass ({team['capacity']} >= {em['people']})"),
        (lambda: (not em["f"]["medical"]) or "medical kit" in team["equipment"],
         lambda: "FAIL (no medical kit)", lambda: "pass"),
    ]
    ok = True
    for name, (test, fail, good) in zip(names, checks):
        if not ok:
            cells[name] = "-"
        elif test():
            cells[name] = good()
        else:
            cells[name] = fail()
            ok = False
    return cells, ok


# ----------------------------------------------------------------- full pipeline
def analyze(messages, hour, teams, manual_blocked=(), auto_cut=True):
    graph, status = road_network(hour, manual_blocked, auto_cut)
    ems, skipped = [], []
    for i, msg in enumerate(messages, 1):
        f, ev = extract_fields(msg)
        if f["zone"] is None:
            skipped.append(dict(idx=i, message=msg))
            continue
        sev_rows, S, s_label = score_severity(f)
        z = zone_record(f["zone"], hour, status)
        d_rows, drs, d_label, D = score_delay_risk(z)
        ems.append(dict(idx=i, tag=f"E{i}", message=msg, f=f, evidence=ev, zone=f["zone"], people=f["people"],
                        sev_rows=sev_rows, S=S, s_label=s_label, record=z, drs_rows=d_rows, DRS=drs,
                        d_label=d_label, D=D, P=priority(S, D), need_type=required_team_type(f)))
    ranked = rank_emergencies(ems)
    for n, e in enumerate(ranked, 1):
        e["rank"] = n

    taken = {}
    for e in ranked:
        grid, feasible = [], []
        for t in teams:
            cells, ok = check_team(e, t, taken)
            routes = None
            if ok:
                path, hrs, trace = a_star(graph, t["base"], e["zone"])
                routes = dict(path=path, hours=hrs, trace=trace)
                if path is None:
                    cells["C6 route exists"] = "FAIL (no open road)"
                    ok = False
                else:
                    cells["C6 route exists"] = f"pass ({hrs:.1f} h)"
            else:
                cells["C6 route exists"] = "-"
            grid.append(dict(team=t["id"], base=t["base"], cells=cells, feasible=ok, route=routes))
            if ok:
                feasible.append(grid[-1])
        e["grid"] = grid
        if feasible:
            best = min(feasible, key=lambda g: (g["route"]["hours"], g["team"]))
            e.update(team=best["team"], route=best["route"], status="assigned",
                     in_time=(e["record"]["lead_hours"] == 0 or best["route"]["hours"] <= e["record"]["lead_hours"]))
            taken[best["team"]] = e["tag"]
        else:
            e.update(team=None, route=None, in_time=False,
                     status="cut off" if any(g["cells"]["C6 route exists"].startswith("FAIL") for g in grid) else "waiting")
    return dict(ranked=ranked, skipped=skipped, graph=graph, road_status=status, hour=hour)
