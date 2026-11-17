"""Run with:  python test_engine.py   (plain asserts, no pytest needed)"""
import math
import data as D
import engine as E

# --- 1. The verified numbers from the Word document (Rev 2) -----------------
MSG = {
    "E1": "Water is rising fast near the bridge. We are trapped and cannot get out. There are 4 people with us, including my grandmother.",
    "E2": "There is a patient at the hospital with a serious medical emergency. The road is partially flooded. Four people are involved.",
    "E3": "The water is rising in our residential area. Four people are inside the house and an elderly person is with us. The road is partially flooded.",
}
sev = {k: E.score_severity(E.extract_fields(m)[0])[1] for k, m in MSG.items()}
assert sev == {"E1": 8, "E2": 6, "E3": 5}, sev
# Zone readings used in the document (explicit records, independent of the Assam data)
rec = {"E1": dict(hazard="High", rise="Fast", open_routes=1, exposed=True, lead_hours=1.5),
       "E2": dict(hazard="Moderate", rise="Stable", open_routes=3, exposed=False, lead_hours=4),
       "E3": dict(hazard="Moderate", rise="Slow", open_routes=2, exposed=True, lead_hours=4)}
out = {k: E.score_delay_risk(r)[1:] for k, r in rec.items()}
assert [out[k][0] for k in MSG] == [12, 2, 6] and [out[k][2] for k in MSG] == [0.6, 0.1, 0.3], out
P = {k: E.priority(sev[k], out[k][2]) for k in MSG}
assert P == {"E1": 12.8, "E2": 6.6, "E3": 6.5}, P
# precedence and bands
assert E.score_severity(E.extract_fields("water is rising fast")[0] | {"zone": "x"})[1] == 2
assert [E.group_points(n) for n in (1, 3, 4, 6, 7, 10, 11)] == [0, 0, 1, 1, 2, 2, 3]
f, _ = E.extract_fields("Water is rising fast and the road is completely blocked. There are 9 of us here, including two children "
                        "and an old man. My phone battery is almost dead.")
assert E.score_severity(f)[1] == 11
# tie-break: E2 (6.6) vs E3 (6.5) -> higher S first
tie = E.rank_emergencies([dict(tag="E3", idx=3, P=6.5, S=5, DRS=6), dict(tag="E2", idx=2, P=6.6, S=6, DRS=2)])
assert [e["tag"] for e in tie] == ["E2", "E3"]

# --- 2. Data sanity ----------------------------------------------------------
assert all(e["a"] in D.COORDS and e["b"] in D.COORDS for e in D.EDGES.values())
for e in D.EDGES.values():   # A* heuristic must never overestimate any road
    assert D.haversine(D.COORDS[e["a"]], D.COORDS[e["b"]]) / D.VMAX <= e["hours"] + 1e-9, e["id"]
g0, st0 = E.road_network(-100)          # long before the wave: everything open
assert all(s == "open" for s in st0.values())
for town in D.COORDS:                   # graph connected
    assert E.a_star(g0, "Guwahati", town)[0] is not None, town

# --- 3. A* correctness: compare with Dijkstra on every pair, at several hours ----
def dijkstra(graph, s, t):
    dist, todo = {s: 0.0}, [(0.0, s)]
    import heapq
    while todo:
        d, n = heapq.heappop(todo)
        if n == t: return d
        if d > dist[n]: continue
        for nb, w, _ in graph[n]:
            if d + w < dist.get(nb, math.inf):
                dist[nb] = d + w; heapq.heappush(todo, (d + w, nb))
    return math.inf
for hour in (-100, 30, 60, 90):
    g, _ = E.road_network(hour)
    for a in D.COORDS:
        for b in D.COORDS:
            _, hrs, _ = E.a_star(g, a, b)
            ref = dijkstra(g, a, b)
            assert (hrs == ref == math.inf) or abs(hrs - ref) < 1e-9, (hour, a, b, hrs, ref)

# --- 4. Re-planning when a road is blocked -----------------------------------
g, _ = E.road_network(-100)
p1, h1, _ = E.a_star(g, "Dibrugarh", "Dhemaji")
assert p1 == ["Dibrugarh", "Dhemaji"]
g2, st = E.road_network(-100, manual_blocked={"r21"})   # close Bogibeel
p2, h2, _ = E.a_star(g2, "Dibrugarh", "Dhemaji")
assert p2 is not None and len(p2) > 2 and h2 > h1, (p2, h2, h1)
# blocking changes the delay-risk factor O for the zone
r_open = E.zone_record("Dhemaji", -100, E.road_network(-100)[1])
r_blk = E.zone_record("Dhemaji", -100, st)
assert r_blk["open_routes"] == r_open["open_routes"] - 1

# --- 5. CSP: a team is never given to two emergencies; priority order matters ----
res = E.analyze(D.PRESET_MESSAGES, 60, D.TEAMS)
used = [e["team"] for e in res["ranked"] if e["team"]]
assert len(used) == len(set(used))
for e in res["ranked"]:
    if e["team"]:
        t = next(t for t in D.TEAMS if t["id"] == e["team"])
        assert t["type"] == e["need_type"] and t["capacity"] >= e["people"]
        assert e["route"]["path"][0] == t["base"] and e["route"]["path"][-1] == e["zone"]
# ranking is sorted by P except inside the 0.5 tie band
Ps = [e["P"] for e in res["ranked"]]
assert all(Ps[i] + E.TIE_BAND >= Ps[i + 1] for i in range(len(Ps) - 1))
# one boat team left, two boat cases: the higher-priority one must get it
teams = [dict(D.TEAMS[0])] + [dict(t, available=False) for t in D.TEAMS[1:]]
r = E.analyze(["Trapped in Dhemaji, water rising fast. 4 people.", "Trapped in Dhubri, water rising. 4 people."], 20, teams)
top, second = r["ranked"]
print("scarce boat:", top["tag"], top["zone"], top["P"], top["status"], "|", second["tag"], second["zone"], second["P"], second["status"])
assert top["team"] == "T1" and second["team"] is None and second["status"] == "waiting"
assert top["P"] >= second["P"] - E.TIE_BAND
# unknown place is skipped, not crashed
r = E.analyze(["Help, we are trapped somewhere"], 0, D.TEAMS)
assert r["skipped"] and not r["ranked"]
# cut-off: Majuli ferries suspended at the peak
r = E.analyze(["Majuli: we are stuck, water rising. 3 people."], 40, D.TEAMS)
assert r["ranked"][0]["status"] == "cut off", r["ranked"][0]["status"]
print("ALL TESTS PASSED")
