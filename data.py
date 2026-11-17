"""Sample data for the Assam-style flood simulation.

Town coordinates are approximate. Roads are a simplified main-highway network
(not survey data). The flood wave is a SIMULATION that moves down the Brahmaputra
valley (east -> west); it is not a record of any real day.
"""
import math

# name: (lat, lon, flood-wave arrival hour, other names the NLP should recognise)
TOWNS = {
    "Tinsukia":        (27.49, 95.35,   0, ["tinsukia"]),
    "Dibrugarh":       (27.47, 94.91,   8, ["dibrugarh"]),
    "Dhemaji":         (27.48, 94.58,  12, ["dhemaji"]),
    "North Lakhimpur": (27.24, 94.10,  20, ["north lakhimpur", "lakhimpur"]),
    "Sivasagar":       (26.98, 94.64,  26, ["sivasagar", "sibsagar"]),
    "Majuli":          (26.95, 94.17,  30, ["majuli"]),
    "Jorhat":          (26.75, 94.20,  36, ["jorhat"]),
    "Golaghat":        (26.52, 93.96,  44, ["golaghat"]),
    "Tezpur":          (26.65, 92.79,  54, ["tezpur"]),
    "Nagaon":          (26.35, 92.68,  60, ["nagaon", "nowgong"]),
    "Morigaon":        (26.25, 92.34,  66, ["morigaon"]),
    "Mangaldoi":       (26.44, 92.03,  68, ["mangaldoi", "mangaldai"]),
    "Guwahati":        (26.14, 91.74,  74, ["guwahati", "gauhati"]),
    "Nalbari":         (26.45, 91.44,  80, ["nalbari"]),
    "Barpeta":         (26.32, 91.00,  86, ["barpeta"]),
    "Goalpara":        (26.18, 90.63,  92, ["goalpara"]),
    "Bongaigaon":      (26.48, 90.56,  96, ["bongaigaon"]),
    "Kokrajhar":       (26.40, 90.27,  98, ["kokrajhar"]),
    "Dhubri":          (26.02, 89.98, 108, ["dhubri"]),
}

# id, a, b, kind, label
#   kind: highway (safe)  low (low-lying road, floods)  bridge  ferry
ROADS = [
    ("r01", "Tinsukia", "Dibrugarh", "low", "Tinsukia - Dibrugarh"),
    ("r02", "Dibrugarh", "Sivasagar", "highway", "Dibrugarh - Sivasagar"),
    ("r03", "Sivasagar", "Jorhat", "highway", "Sivasagar - Jorhat"),
    ("r04", "Jorhat", "Golaghat", "highway", "Jorhat - Golaghat"),
    ("r05", "Golaghat", "Nagaon", "low", "Golaghat - Nagaon (via Kaziranga)"),
    ("r06", "Nagaon", "Guwahati", "highway", "Nagaon - Guwahati"),
    ("r07", "Nagaon", "Morigaon", "low", "Nagaon - Morigaon"),
    ("r08", "Morigaon", "Guwahati", "low", "Morigaon - Guwahati"),
    ("r09", "Guwahati", "Goalpara", "highway", "Guwahati - Goalpara"),
    ("r10", "Goalpara", "Dhubri", "low", "Goalpara - Dhubri"),
    ("r11", "Goalpara", "Bongaigaon", "bridge", "Naranarayan Setu (Goalpara - Bongaigaon)"),
    ("r12", "Bongaigaon", "Kokrajhar", "highway", "Bongaigaon - Kokrajhar"),
    ("r13", "Kokrajhar", "Dhubri", "low", "Kokrajhar - Dhubri"),
    ("r14", "Dhemaji", "North Lakhimpur", "low", "Dhemaji - North Lakhimpur"),
    ("r15", "North Lakhimpur", "Tezpur", "highway", "North Lakhimpur - Tezpur"),
    ("r16", "Tezpur", "Mangaldoi", "highway", "Tezpur - Mangaldoi"),
    ("r17", "Mangaldoi", "Nalbari", "highway", "Mangaldoi - Nalbari"),
    ("r18", "Nalbari", "Barpeta", "low", "Nalbari - Barpeta"),
    ("r19", "Barpeta", "Bongaigaon", "low", "Barpeta - Bongaigaon"),
    ("r20", "Nalbari", "Guwahati", "bridge", "Saraighat Bridge (Nalbari - Guwahati)"),
    ("r21", "Dibrugarh", "Dhemaji", "bridge", "Bogibeel Bridge (Dibrugarh - Dhemaji)"),
    ("r22", "Tezpur", "Nagaon", "bridge", "Kolia Bhomora Setu (Tezpur - Nagaon)"),
    ("r23", "Jorhat", "Majuli", "ferry", "Ferry (Jorhat - Majuli)"),
    ("r24", "North Lakhimpur", "Majuli", "ferry", "Ferry (North Lakhimpur - Majuli)"),
]

WINDING = {"highway": 1.3, "low": 1.3, "bridge": 1.2, "ferry": 1.1}
SPEED = {"highway": 40, "low": 40, "bridge": 40, "ferry": 20}   # km/h, 40 is the maximum
VMAX = 40.0


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


COORDS = {n: (v[0], v[1]) for n, v in TOWNS.items()}
ARRIVAL = {n: v[2] for n, v in TOWNS.items()}
ALIASES = {alias: n for n, v in TOWNS.items() for alias in v[3]}
UPSTREAM_ORDER = sorted(TOWNS, key=lambda n: ARRIVAL[n])

EDGES = {}
for rid, a, b, kind, label in ROADS:
    km = haversine(COORDS[a], COORDS[b]) * WINDING[kind]
    EDGES[rid] = dict(id=rid, a=a, b=b, kind=kind, label=label, km=round(km, 1),
                      hours=km / SPEED[kind], exposed=kind != "highway")

# Rescue teams. 'equipment' is what the team physically carries.
TEAMS = [
    dict(id="T1", type="boat",    capacity=8,  equipment={"boat", "life jackets"},   base="Guwahati", available=True),
    dict(id="T2", type="boat",    capacity=6,  equipment={"boat", "life jackets"},   base="Jorhat",   available=True),
    dict(id="T3", type="boat",    capacity=6,  equipment={"boat", "life jackets"},   base="Dibrugarh", available=True),
    dict(id="T4", type="boat",    capacity=6,  equipment={"boat", "life jackets"},   base="Dhubri",   available=True),
    dict(id="T5", type="boat",    capacity=2,  equipment={"boat", "life jackets"},   base="Tezpur",   available=True),
    dict(id="T6", type="medical", capacity=6,  equipment={"medical kit", "vehicle"}, base="Guwahati", available=True),
    dict(id="T7", type="medical", capacity=5,  equipment={"medical kit", "vehicle"}, base="Tezpur",   available=True),
    dict(id="T8", type="ground",  capacity=12, equipment={"vehicle"},                base="Nagaon",   available=True),
    dict(id="T9", type="ground",  capacity=8,  equipment={"vehicle"},                base="Barpeta",  available=True),
]
EQUIPMENT_NEEDED = {"boat": {"boat", "life jackets"}, "medical": {"medical kit"}, "ground": {"vehicle"}}

PRESET_MESSAGES = [
    "Water is rising fast in Dhemaji. We are trapped on the roof, 6 people including two children. Please send a boat.",
    "Majuli: we are stuck, the water is rising and the road is blocked. 8 of us here with an elderly woman and a child. My phone battery is almost dead.",
    "Jorhat hospital: a patient is unconscious and bleeding, water is entering the ward. 4 people. Evacuate immediately.",
    "Morigaon: road is partially flooded and we are stuck. 12 people, a grandfather who cannot walk.",
    "Barpeta: water is rising, we are stuck with 5 people and a baby. No signal.",
    "Dhubri riverbank: water rising quickly, we are trapped. 3 people.",
    "Guwahati low-lying colony: road flooded, 7 people with elderly parents. Need evacuation now.",
    "Tezpur: serious injury, road blocked, ambulance cannot reach. 2 people.",
    "Dibrugarh: water rising rapidly near the river, 4 people trapped.",
    "Nagaon: roads closed and water is rising. 10 of us in a school building.",
]
