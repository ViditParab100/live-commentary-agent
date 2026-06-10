#!/usr/bin/env python3
"""
Torn Racing Spy — HTTP listener (port 8766).
Receives race_state events from the TamperMonkey script and prints a live leaderboard.

Usage:
    python ws_listener.py
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from pathlib import Path

from event_detector import EventDetector

# Force UTF-8 output on Windows so block chars print correctly
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OUT_DIR = Path("spy_results")
OUT_DIR.mkdir(exist_ok=True)
_stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
session_file = OUT_DIR / f"session_{_stamp}.jsonl"   # raw frames
events_file  = OUT_DIR / f"events_{_stamp}.jsonl"    # detected events (for commentary worker)
events_file.touch()   # create immediately so commentary_worker finds this session's file

update_count = 0
detector = None   # created in main() after args are parsed


def ts(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S")


def bar(pct, width=20):
    if pct is None: return '?' * width
    filled = round(pct / 100 * width)
    return '#' * filled + '.' * (width - filled)


def handle_race_state(ev):
    global update_count
    update_count += 1

    data    = ev.get('data', {})
    drivers = data.get('drivers', [])
    my_info = data.get('my_info') or {}
    track   = data.get('track', '?')
    laps    = data.get('laps', '?')
    status  = data.get('status', '?')
    t       = ts(ev.get('ts', 0))

    # --- Run event detection (stateful across frames) ---
    events = detector.process(ev)

    # --- Print leaderboard ---
    print(f"\n{'-'*62}")
    print(f"  #{update_count:<4}  {t}   {track}  ·  {laps} laps  ·  {status}")
    print(f"{'-'*62}")
    print(f"  {'POS':<4} {'DRIVER':<22} {'COMPLETION':>10}   TRACK PROGRESS")
    print(f"  {'-'*58}")

    for d in drivers:
        name  = d.get('name', '?')
        pos   = d.get('position', '?')
        comp  = d.get('completion')
        is_me = name == my_info.get('name')
        flag  = ' ★' if is_me else '  '
        comp_str = f"{comp:.2f}%" if comp is not None else "   ?%"
        b = bar(comp)
        line = f"  {pos:<4} {name[:20]+flag:<22} {comp_str:>10}   {b}"
        print(line)

    if my_info:
        print(f"\n  My lap: {my_info.get('lap','?')}  ·  "
              f"Last lap: {my_info.get('last_lap','?')}  ·  "
              f"Position: {my_info.get('position','?')}")

    # --- Print + persist detected events (priority-sorted, highest first) ---
    for e in sorted(events, key=lambda x: -x['priority']):
        print(f"  [EVENT P{e['priority']}] {e['type']:<13} {e['message']}")
        with open(events_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(e) + '\n')

    # --- Canvas marker debug ---
    cm = data.get('canvas_markers')
    if cm:
        if 'error' in cm:
            print(f"  canvas: TAINTED — {cm['error']}")
        else:
            markers = cm.get('markers', [])
            mode = 'CANVAS MODE' if len(markers) >= len(drivers) else f'path mode ({len(markers)} markers, need {len(drivers)})'
            print(f"  canvas: {cm.get('w','?')}×{cm.get('h','?')}  {len(markers)} clusters  [{mode}]")
            for i, m in enumerate(markers[:8]):
                print(f"    [{i}] x={m['x']:>3} y={m['y']:>3}  rgb({m['r']},{m['g']},{m['b']})  size={m['size']}")

    sys.stdout.flush()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/data':
            self.send_response(404); self.end_headers(); return

        length = int(self.headers.get('Content-Length', 0))
        raw    = self.rfile.read(length)

        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            batch = json.loads(raw)
            if not isinstance(batch, list):
                batch = [batch]

            for ev in batch:
                with open(session_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(ev) + '\n')

                if ev.get('type') == 'race_state':
                    handle_race_state(ev)
                elif ev.get('type') == 'connected':
                    print(f"\n  Browser connected  —  {ev.get('data', {}).get('href', '')}")
                    sys.stdout.flush()

        except Exception as e:
            print(f"[ERROR] {e}")
            sys.stdout.flush()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    global detector

    ap = argparse.ArgumentParser(description="Torn Racing Spy — Live Leaderboard Listener")
    ap.add_argument(
        "--reverse-rank", action="store_true",
        help="Force reverse ranking for all races (last→1st). "
             "Races named 'KOSL' are auto-reversed regardless of this flag.",
    )
    args = ap.parse_args()

    detector = EventDetector(reverse_rank=args.reverse_rank)

    port = 8766
    mode_tag = "  [REVERSE RANK mode — last place scores first]\n" if args.reverse_rank else ""
    print(f"\n{'#'*62}")
    print(f"  TORN RACING SPY  —  Live Leaderboard Listener")
    print(f"  http://localhost:{port}")
    print(f"  Session log: {session_file.resolve()}")
    print(f"  Events log : {events_file.resolve()}")
    print(f"{'#'*62}\n")
    if mode_tag:
        print(mode_tag)
    print("  Waiting for race data...\n")
    sys.stdout.flush()
    HTTPServer(('localhost', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
