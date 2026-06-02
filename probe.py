#!/usr/bin/env python3
"""
Torn City Racing API Probe
Hits every known racing-related endpoint and dumps raw JSON to probe_results/.
Run this first to discover exactly what data fields the API exposes.

Usage:
    python probe.py                     # reads TORN_API_KEY from .env
    python probe.py <YOUR_API_KEY>      # pass key directly
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# API key resolution: .env → sys.argv → exit
# ---------------------------------------------------------------------------
API_KEY = os.getenv("TORN_API_KEY")
if not API_KEY:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        API_KEY = os.getenv("TORN_API_KEY")
    except ImportError:
        pass

if not API_KEY and len(sys.argv) > 1:
    API_KEY = sys.argv[1]

if not API_KEY:
    print("ERROR: No API key found.")
    print("  Option 1: copy .env.example → .env and set TORN_API_KEY")
    print("  Option 2: python probe.py <YOUR_API_KEY>")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BASE_URL = "https://api.torn.com"
BASE_URL_V2 = "https://api.torn.com/v2"
OUT_DIR = Path("probe_results")
OUT_DIR.mkdir(exist_ok=True)


def get(path: str, selections: str = "", extra_params: dict = None, v2: bool = False) -> tuple[int | None, dict]:
    base = BASE_URL_V2 if v2 else BASE_URL
    params = {"key": API_KEY}
    if selections:
        params["selections"] = selections
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(f"{base}{path}", params=params, timeout=10)
        return r.status_code, r.json()
    except Exception as e:
        return None, {"_probe_error": str(e)}


def save_result(name: str, data: dict):
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def summarise_fields(data, depth=0, max_depth=3):
    """Recursively print field names and value previews."""
    pad = "    " * depth
    if depth > max_depth:
        return
    if isinstance(data, dict):
        for k, v in list(data.items())[:30]:
            if isinstance(v, dict):
                print(f"{pad}{k}:  {{dict, {len(v)} keys}}")
                summarise_fields(v, depth + 1, max_depth)
            elif isinstance(v, list):
                inner = f"list[{len(v)}]"
                if v and isinstance(v[0], dict):
                    inner += f"  — first item has keys: {list(v[0].keys())[:8]}"
                print(f"{pad}{k}:  {inner}")
                if v and isinstance(v[0], dict):
                    summarise_fields(v[0], depth + 1, max_depth)
            else:
                preview = repr(v)
                if len(preview) > 80:
                    preview = preview[:77] + "..."
                print(f"{pad}{k}:  {preview}")
    elif isinstance(data, list):
        print(f"{pad}[list of {len(data)} items]")
        if data and isinstance(data[0], dict):
            summarise_fields(data[0], depth, max_depth)


def probe(label: str, path: str, selections: str = "", extra_params: dict = None, v2: bool = False):
    base_display = "v2" if v2 else "v1"
    sel_display = selections or "<none>"
    print(f"\n{'='*60}")
    print(f"  [{base_display}] GET {path}  selections={sel_display}")
    print(f"{'='*60}")

    status, data = get(path, selections, extra_params, v2=v2)
    print(f"  HTTP status : {status}")

    if "_probe_error" in data:
        print(f"  Request error: {data['_probe_error']}")
        return data

    if "error" in data:
        print(f"  API error   : {data['error']}")
    else:
        saved = save_result(label, data)
        print(f"  Saved       : {saved}")
        print(f"  Field map   :")
        summarise_fields(data)

    return data


# ---------------------------------------------------------------------------
# Phase 1 — v1 sweep (kept for reference)
# ---------------------------------------------------------------------------
print(f"\n{'#'*60}")
print(f"  TORN RACING API PROBE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'#'*60}")

print("\n--- v1 endpoints ---")
data_racing_root   = probe("01_v1_racing_root",        "/racing/")
data_user_racing   = probe("02_v1_user_racing",         "/user/",   selections="racing")
data_torn_racing   = probe("03_v1_torn_racingStats",    "/torn/",   selections="racingStats")

time.sleep(0.5)

# ---------------------------------------------------------------------------
# Phase 2 — v2 sweep (the API told us 'races' requires v2)
# ---------------------------------------------------------------------------
print("\n--- v2 endpoints ---")

# List active/recent races
data_v2_races      = probe("04_v2_races",               "/racing/races",          v2=True)
data_v2_race_root  = probe("05_v2_racing_root",         "/racing/",               v2=True)
data_v2_user       = probe("06_v2_user",                "/user/",                 v2=True)
data_v2_user_races = probe("07_v2_user_races",          "/user/",   selections="races",  v2=True)

# Try common v2 racing sub-resources
data_v2_tracks     = probe("08_v2_tracks",              "/racing/tracks",         v2=True)
data_v2_cars       = probe("09_v2_cars",                "/racing/cars",           v2=True)
data_v2_lookup     = probe("10_v2_lookup",              "/racing/lookup",         v2=True)

time.sleep(1)

# ---------------------------------------------------------------------------
# Phase 2 — if we found race IDs, probe individual races
# ---------------------------------------------------------------------------
print(f"\n\n{'#'*60}")
print(f"  PROBING INDIVIDUAL RACES (if IDs found)")
print(f"{'#'*60}")

race_ids = []

for data in [data_v2_races, data_v2_user_races, data_v2_race_root, data_racing_root, data_user_racing]:
    if not isinstance(data, dict):
        continue
    for key in ["races", "current", "active", "race_id", "ID"]:
        val = data.get(key)
        if isinstance(val, list) and val:
            for item in val[:3]:
                rid = item.get("id") or item.get("race_id") or item.get("ID")
                if rid:
                    race_ids.append(str(rid))
        elif isinstance(val, dict):
            race_ids.extend(list(val.keys())[:3])
        elif isinstance(val, (int, str)) and val:
            race_ids.append(str(val))

race_ids = list(dict.fromkeys(race_ids))[:3]  # dedupe, cap at 3

if race_ids:
    print(f"\n  Found race IDs: {race_ids}")
    for rid in race_ids:
        time.sleep(0.5)
        probe(f"11_v1_race_{rid}",          f"/racing/{rid}/")
        probe(f"12_v2_race_{rid}",          f"/racing/races/{rid}",             v2=True)
        probe(f"13_v2_race_{rid}_entrants", f"/racing/races/{rid}/entrants",    v2=True)
        probe(f"14_v2_race_{rid}_log",      f"/racing/races/{rid}/log",         v2=True)
else:
    print("\n  No race IDs found in responses above.")
    print("  Try running during an active race, or check probe_results/ for clues.")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n\n{'#'*60}")
print(f"  PROBE COMPLETE")
print(f"  Results saved to: {OUT_DIR.resolve()}")
print(f"{'#'*60}")
print()
print("Key questions to answer from the JSON files:")
print("  1. Is there a 'progress' or 'distance' field per racer? (for map positioning)")
print("  2. Is there a 'speed' or 'velocity' field? (for overtake prediction)")
print("  3. What does 'position' look like — rank integer or track coordinate?")
print("  4. How many racers per race? What fields describe each?")
print("  5. Is there a race status field (active/finished/waiting)?")
print("  6. What is the polling frequency cap before rate-limiting?")
print()
