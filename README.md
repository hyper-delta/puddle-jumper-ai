# Cloudburst emergency coordination (Assam flood simulation)

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://puddle-jumper-ai.streamlit.app/)

**Live demo:** https://puddle-jumper-ai.streamlit.app/

Run locally (Python 3.10+, internet needed for map imagery):

    python -m pip install -r requirements.txt
    pyhton -m streamlit run app.py

Check the decision logic on its own:

    python test_engine.py        # prints ALL TESTS PASSED

## What is where
- `app.py`        page layout, reports and teams editors, step-by-step decision trace
- `console.py`    the operations console (map + dispatch queue + time controls) as a Streamlit custom component
- `static/`       the built console (JS and CSS, includes the MapLibre GL map engine). Nothing to install or build to run the app
- `frontend/`     source of the console. Only needed if you want to change it: `cd frontend && npm install && npm run build`
- `engine.py`     NLP fields, severity, delay risk, priority, CSP team assignment, A* routing
- `data.py`       towns, roads, teams, sample reports
- `.streamlit/config.toml`  light and dark theme

## Using the console
- Basemaps: Satellite (Esri World Imagery with place names), Terrain, Streets, Dark. "3D terrain" tilts the map over real elevation.
- Time: press play, drag the flood-stage curve, use the step buttons, or the left and right arrow keys while the curve is focused.
- Click a numbered circle or a queue row to inspect an incident. The Decision trace tab below follows the same selection.
- Zoom and pan are never reset by updates. "Reset view" returns to the full-state view.
- Close roads and toggle automatic flood closures in the sidebar. Edit reports and teams in their tabs.

## Map data sources (all keyless)
Esri World Imagery, World Boundaries and Places, World Topo Map, World Street Map, Canvas Dark Gray, and AWS terrain tiles for 3D.
Their attribution shows on the map. Keep it if you publish screenshots.
