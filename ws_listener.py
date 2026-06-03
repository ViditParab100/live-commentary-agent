#!/usr/bin/env python3
"""
Torn Racing Spy — HTTP listener (port 8766).
Receives race_state events from the TamperMonkey script and prints a live leaderboard.

Usage:
    python ws_listener.py
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from pathlib import Path

OUT_DIR = Path("spy_results")
OUT_DIR.mkdir(exist_ok=True)
session_file = OUT_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

# Track previous driver order to detect overtakes
prev_order: list[str] = []
update_count = 0


def ts(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S")


def bar(pct, width=20):
    if pct is None: return '?' * width
    filled = round(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


def detect_overtakes(old_order, new_order):
    """Return list of (overtaker, overtaken) tuples."""
    events = []
    for new_pos, name in enumerate(new_order):
        if name in old_order:
            old_pos = old_order.index(name)
            if old_pos > new_pos:
                # moved up — find who they passed
                for passed in old_order[new_pos:old_pos]:
                    if passed in new_order:
                        events.append((name, passed))
    return events


def handle_race_state(ev):
    global prev_order, update_count
    update_count += 1

    data    = ev.get('data', {})
    drivers = data.get('drivers', [])
    my_info = data.get('my_info') or {}
    track   = data.get('track', '?')
    laps    = data.get('laps', '?')
    status  = data.get('status', '?')
    t       = ts(ev.get('ts', 0))

    new_order = [d['name'] for d in drivers]

    # --- Detect overtakes ---
    overtakes = detect_overtakes(prev_order, new_order) if prev_order else []
    prev_order = new_order

    # --- Print leaderboard ---
    print(f"\n{'─'*62}")
    print(f"  #{update_count:<4}  {t}   {track}  ·  {laps} laps  ·  {status}")
    print(f"{'─'*62}")
    print(f"  {'POS':<4} {'DRIVER':<22} {'COMPLETION':>10}   TRACK PROGRESS")
    print(f"  {'─'*58}")

    for d in drivers:
        name  = d.get('name', '?')
        pos   = d.get('position', '?')
        comp  = d.get('completion')
        is_me = name == my_info.get('name')
        flag  = ' ★' if is_me else '  '
        comp_str = f"{comp:.2f}%" if comp is not None else "   ?%"
        b = bar(comp)
        marker = ''
        for (overtaker, overtaken) in overtakes:
            if name == overtaker: marker = ' ⬆ OVERTAKE!'
            if name == overtaken: marker = ' ⬇'
        line = f"  {pos:<4} {name[:20]+flag:<22} {comp_str:>10}   {b}{marker}"
        print(line)

    if my_info:
        print(f"\n  My lap: {my_info.get('lap','?')}  ·  "
              f"Last lap: {my_info.get('last_lap','?')}  ·  "
              f"Position: {my_info.get('position','?')}")

    if overtakes:
        print()
        for overtaker, overtaken in overtakes:
            print(f"  *** {overtaker} overtook {overtaken}! ***")

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
    port = 8766
    print(f"\n{'#'*62}")
    print(f"  TORN RACING SPY  —  Live Leaderboard Listener")
    print(f"  http://localhost:{port}")
    print(f"  Session log: {session_file.resolve()}")
    print(f"{'#'*62}\n")
    print("  Waiting for race data...\n")
    sys.stdout.flush()
    HTTPServer(('localhost', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
