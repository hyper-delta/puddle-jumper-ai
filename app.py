"""Cloudburst emergency coordination: interactive Assam-style flood simulation.
Run:  streamlit run app.py
"""
import altair as alt
import pandas as pd
import streamlit as st

import data as D
import engine as E
import console as C

st.set_page_config(page_title="Cloudburst emergency coordination", page_icon=":material/flood:", layout="wide")

TOWN_NAMES = sorted(D.TOWNS)
STEPS = ["Extract", "Severity", "Delay risk", "Priority", "Assignment", "Route", "Dispatch"]
ss = st.session_state
ss.setdefault("base_messages", list(D.PRESET_MESSAGES))
ss.setdefault("current_messages", list(D.PRESET_MESSAGES))
ss.setdefault("msg_version", 0)


def load_messages(msgs):
    ss.base_messages, ss.current_messages = list(msgs), list(msgs)
    ss.msg_version += 1


# ------------------------------------------------------------------ layout, created in reading order
st.title("Cloudburst emergency coordination")
st.caption("A rule-based agent reads each report, ranks it, matches a rescue team and plans the route. "
           "The flood wave, towns and roads are simulated, not a record of a real day.")
console_box = st.container()
tab_trace, tab_reports, tab_teams, tab_roads, tab_wave, tab_about = st.tabs(
    [":material/account_tree: Decision trace", ":material/edit_note: Incident reports", ":material/groups: Rescue teams",
     ":material/alt_route: Roads", ":material/timeline: Flood timeline", ":material/info: About"])
team_editor_box, team_result_box = tab_teams.container(), tab_teams.container()

# ------------------------------------------------------------------ inputs (must be declared before the analysis runs)
with st.sidebar:
    st.header("Scenario")
    auto_cut = st.toggle("Floodwater closes low-lying roads and ferries", value=True)
    blocked_labels = st.multiselect("Close roads manually", [e["label"] for e in D.EDGES.values()],
                                    help="Closed roads are removed from every route search.")
    manual_blocked = {e["id"] for e in D.EDGES.values() if e["label"] in blocked_labels}
    st.caption("Time, basemap and map layers are controlled on the map. Reports and teams are edited in the tabs below it.")

with tab_reports:
    b1, b2, _ = st.columns([1.3, 1, 4])
    b1.button("Load Assam scenario", on_click=load_messages, args=(D.PRESET_MESSAGES,), width="stretch")
    b2.button("Clear all", on_click=load_messages, args=([],), width="stretch")
    with st.form("add_report", clear_on_submit=True, border=False):
        new_msg = st.text_area("New report", placeholder="Water is rising fast in Barpeta. We are trapped, 5 people.", height=80)
        added = st.form_submit_button("Add report", icon=":material/add:")
    if added and new_msg.strip():
        load_messages(ss.current_messages + [new_msg.strip()])
        st.rerun()
    edited = st.data_editor(pd.DataFrame({"message": pd.Series(ss.base_messages, dtype="object")}), key=f"msgs_{ss.msg_version}",
                            num_rows="dynamic", width="stretch", hide_index=True,
                            column_config={"message": st.column_config.TextColumn("Report text (edit a cell or delete a row)", width="large")})
    messages = [m for m in edited["message"] if isinstance(m, str) and m.strip()]
    ss.current_messages = messages
    st.caption("Incident numbers (E1, E2, ...) follow the order of this list. Each report must name one of the mapped towns.")

with team_editor_box:
    team_df = pd.DataFrame([dict(Team=t["id"], Type=t["type"], Base=t["base"], Capacity=t["capacity"], Free=t["available"])
                            for t in D.TEAMS])
    team_edit = st.data_editor(team_df, key="teams", hide_index=True, width="stretch", disabled=["Team", "Type"],
                               column_config={"Base": st.column_config.SelectboxColumn(options=TOWN_NAMES),
                                              "Capacity": st.column_config.NumberColumn(min_value=1, max_value=30, step=1)})
    base_by_id = {t["id"]: t for t in D.TEAMS}
    teams = [dict(base_by_id[r.Team], base=r.Base, capacity=int(r.Capacity), available=bool(r.Free)) for r in team_edit.itertuples()]

# ------------------------------------------------------------------ analysis
hour, console_pick = C.console_state()
res = E.analyze(messages, hour, teams, manual_blocked, auto_cut)
ranked, status = res["ranked"], res["road_status"]
by_tag = {e["tag"]: e for e in ranked}
tags = [e["tag"] for e in ranked]

# a click on the map or in the queue selects an incident; so does the picker in the Decision trace tab
if console_pick and console_pick != ss.get("_seen_pick"):
    ss.sel_tag = console_pick
ss._seen_pick = console_pick
if ss.get("sel_tag") not in tags:
    ss.sel_tag = tags[0] if tags else None
sel = by_tag.get(ss.sel_tag)

with console_box:
    C.show(C.payload(hour, res, teams, ss.sel_tag))
    if res["skipped"]:
        st.warning("No known town found in " + ", ".join(f"E{s['idx']}" for s in res["skipped"]) + ". Known towns: " + ", ".join(TOWN_NAMES))

# ------------------------------------------------------------------ decision trace
with tab_trace:
    if not ranked:
        st.info("Add or load reports to see the decision steps.")
    else:
        e = sel
        c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
        c1.selectbox("Incident", tags, key="sel_tag",
                     format_func=lambda t: f"#{by_tag[t]['rank']}  {t}  {by_tag[t]['zone']}  (P {by_tag[t]['P']})")
        step = c2.segmented_control("Step", STEPS, default=STEPS[0], required=True, key="step", width="stretch")
        st.info(f"“{e['message']}”")

        if step == "Extract":
            st.markdown("The NLP step turns free text into a fixed list of fields. It scores nothing yet.")
            rows = [{"Field": lbl, "Value": "-" if e["f"][k] is None else "yes" if e["f"][k] is True else "no" if e["f"][k] is False else str(e["f"][k]),
                     "Found in message": f"“{e['evidence'][k]}”" if e["evidence"][k] else "-"} for k, lbl in E.FIELD_LABELS]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        elif step == "Severity":
            st.markdown("Severity adds the points of every rule that matches. Where two rules describe the same thing, only the stronger one counts.")
            st.dataframe(pd.DataFrame([{"Rule": r["rule"], "Meaning": r["meaning"], "Points": f"+{r['points']}",
                                        "Counted": "yes" if r["counted"] else "no, " + r["note"]} for r in e["sev_rows"]]),
                         hide_index=True, width="stretch")
            used = [str(r["points"]) for r in e["sev_rows"] if r["counted"]]
            st.success(f"S = {' + '.join(used) or '0'} = **{e['S']}**, {e['s_label']} (0 to 2 low, 3 to 5 medium, 6 and above high)")
        elif step == "Delay risk":
            st.markdown(f"Delay risk asks how much worse things get if we wait. It is read from the zone record of {e['zone']} "
                        f"at +{hour} h, not from the message.")
            st.dataframe(pd.DataFrame([{"Factor": r["factor"], "Meaning": r["meaning"], "Zone reading": r["reading"],
                                        "Points": r["points"]} for r in e["drs_rows"]]), hide_index=True, width="stretch")
            st.success(f"DRS = {' + '.join(str(r['points']) for r in e['drs_rows'])} = **{e['DRS']}**, {e['d_label']}, "
                       f"D = **{e['D']}** (0 to 3 gives 0.1, 4 to 7 gives 0.3, 8 to 13 gives 0.6)")
            st.caption("Move the time slider or close a road in the sidebar and watch this table change.")
        elif step == "Priority":
            st.markdown("Priority combines severity and delay risk. All incidents are then ranked.")
            st.success(f"P = S + D x S = {e['S']} + {e['D']} x {e['S']} = {e['S']} + {round(e['D'] * e['S'], 2)} = **{e['P']}**, rank **{e['rank']}** of {len(ranked)}")
            st.dataframe(pd.DataFrame([{"Rank": x["rank"], "ID": x["tag"], "Town": x["zone"], "S": x["S"], "DRS": x["DRS"],
                                        "D": x["D"], "P": x["P"]} for x in ranked]), hide_index=True, width="stretch")
            st.caption(f"Priorities within {E.TIE_BAND} of each other are a near tie: higher S goes first, then higher DRS, then the earlier report.")
        elif step == "Assignment":
            st.markdown(f"Teams are assigned in priority order, so scarce teams go to the most urgent case. "
                        f"{e['tag']} needs a {e['need_type']} team for {e['people']} people.")
            st.dataframe(pd.DataFrame([{"Team": g["team"], "Base": g["base"], **g["cells"], "Result": "Feasible" if g["feasible"] else "Removed"}
                                       for g in e["grid"]]), hide_index=True, width="stretch")
            st.caption("C1 free and not given to a higher-priority case. C2 right team type. C3 equipment. C4 capacity at least the group size. "
                       "C5 medical kit for medical cases. C6 an open road from the team's base to the town.")
            if e["team"]:
                st.success(f"{e['tag']} is assigned to **{e['team']}**, the fastest route among the feasible teams.")
            elif e["status"] == "cut off":
                st.error("A suitable team exists, but floodwater has closed every road or ferry into this town. Escalate to boat or air rescue.")
            else:
                st.warning("No feasible team right now. The request waits in the queue until a team is free.")
        elif step == "Route":
            if not e["route"]:
                (st.error if e["status"] == "cut off" else st.warning)(
                    f"No route. Every road and ferry into {e['zone']} is closed right now." if e["status"] == "cut off"
                    else "No route because no team was selected for this incident.")
            else:
                r = e["route"]
                st.markdown(f"A* search from {e['team']}'s base to {e['zone']}. f = g + h, where g is travel time so far and h is "
                            "straight-line distance divided by top speed. h never overestimates, so the route found is the fastest.")
                st.dataframe(pd.DataFrame([{"Step": i + 1, "Expand": t["node"], "g (h)": t["g"], "h (h)": t["h"], "f = g + h": t["f"]}
                                           for i, t in enumerate(r["trace"])]), hide_index=True, width="stretch")
                st.success(f"Route: **{' > '.join(r['path'])}**, {r['hours']:.1f} h")
                st.caption("Degraded roads count 2.5 times the travel time and blocked roads are not used.")
        else:
            if e["team"]:
                lead = e["record"]["lead_hours"]
                st.success(f"Dispatch team **{e['team']}** to {e['zone']} for {e['tag']}, priority rank {e['rank']}.")
                st.write(f"Route {' > '.join(e['route']['path'])}, ETA {e['route']['hours']:.1f} h. "
                         + ("The town is already flooded." if lead == 0 else
                            f"The wave arrives in {lead:g} h, so the team arrives " + ("in time." if e["in_time"] else "late.")))
            else:
                st.error(f"No dispatch for {e['tag']} ({e['zone']}): {e['status']}.")

# ------------------------------------------------------------------ teams, roads, timeline, about
with team_result_box:
    assigned = {x["team"]: x for x in ranked if x["team"]}
    st.dataframe(pd.DataFrame([{"Team": t["id"], "Type": t["type"], "Base": t["base"], "Capacity": t["capacity"],
                                "Equipment": ", ".join(sorted(t["equipment"])), "Free": "yes" if t["available"] else "no",
                                "Assigned to": (f"{assigned[t['id']]['tag']} {assigned[t['id']]['zone']}" if t["id"] in assigned else "-"),
                                "ETA (h)": f"{assigned[t['id']]['route']['hours']:.1f}" if t["id"] in assigned else "-"} for t in teams]),
                 hide_index=True, width="stretch")
    st.caption("Change a team's base, capacity or availability in the table above. Assignments update immediately.")

with tab_roads:
    st.dataframe(pd.DataFrame([{"Road": e["label"], "Type": e["kind"], "km": e["km"], "Normal time (h)": round(e["hours"], 1),
                                "Status now": status[rid]} for rid, e in D.EDGES.items()]), hide_index=True, width="stretch")
    st.caption("Low-lying roads degrade when the wave reaches a town and are cut shortly after. Ferries stop at the peak. "
               "Bridges and highways stay open unless you close them in the sidebar.")

with tab_wave:
    rows = [dict(Town=n, Hour=h, Hazard=E.HAZARD_PTS[E.zone_phase(n, h)[0]]) for n in D.UPSTREAM_ORDER for h in range(0, 145, 6)]
    heat = alt.Chart(pd.DataFrame(rows)).mark_rect().encode(
        x=alt.X("Hour:O", title="Hours since the wave reached Tinsukia"),
        y=alt.Y("Town:N", sort=D.UPSTREAM_ORDER, title=None, axis=alt.Axis(labelOverlap=False)),
        color=alt.Color("Hazard:Q", scale=alt.Scale(domain=[0, 3]), legend=alt.Legend(title="Hazard", values=[0, 1, 2, 3])),
        tooltip=["Town", "Hour", "Hazard"])
    now = alt.Chart(pd.DataFrame({"Hour": [hour]})).mark_rule(color="#EB6834", strokeWidth=3).encode(x="Hour:O")
    st.altair_chart((heat + now).properties(height=520), width="stretch")
    st.caption("Each row is a town, upstream at the top. Hazard runs from 0 (low) to 3 (extreme). The orange line is the current simulation time.")

with tab_about:
    st.markdown("""
**What this is.** A hybrid decision agent for flash-flood emergencies. Rules and search do the reasoning, so every decision can be explained.

**Pipeline.** Report, then NLP (fields), rules (severity S), zone data (delay risk D), priority P = S + D x S,
CSP (which team), A* (which road), dispatch.

**Model assumptions**
- The flood wave is a simple simulation moving east to west. It is not a record of any real flood.
- Town coordinates are approximate and the road network is a simplified set of main highways, bridges and ferries.
- NLP is keyword matching, so reports must name one of the towns on the map.
- One team per incident, assigned greedily in priority order.
- All reports are known when the pipeline runs. There is no re-assignment after a team is dispatched.
""")
