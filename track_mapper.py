#!/usr/bin/env python3
"""
Track mapper — turns the 2-D race into a 1-D arc-length model so that the
along-track distance between cars can be computed in the correct direction.

Pipeline
--------
1. build_centerline(session)  -> ordered [{s, x, y}] traced from the player's
   marker positions, parameterised by lap fraction s in [0, 1).
2. TrackMap.project(x, y)      -> s : where a pixel position sits along the lap.
3. TrackMap.gap(s_ahead, s_behind) -> forward arc distance (laps), 0..1.

The cleanest distance signal is actually `completion` from the DOM
(completion * laps) % 1 == s, but projecting canvas pixels lets us place
markers on the image and gives finer spatial resolution than the 0.01%
completion step.
"""

import json
import math
from pathlib import Path


def build_centerline(session_path, num_bins=72):
    """Trace the track centerline from the player's gold marker over a session."""
    lines = [l for l in Path(session_path).read_text(encoding='utf-8', errors='replace').split('\n') if l.strip()]
    bins = [[] for _ in range(num_bins)]

    for l in lines:
        ev = json.loads(l)
        if ev.get('type') != 'race_state':
            continue
        d = ev['data']
        mi = d.get('my_info') or {}
        comp = mi.get('completion')
        laps = d.get('laps') or 1
        cm = d.get('canvas_markers') or {}
        if comp is None:
            continue
        # Player's gold marker: high R, mid G, low B
        gold = [m for m in cm.get('markers', []) if m['r'] > 170 and 120 < m['g'] < 175 and m['b'] < 95]
        if not gold:
            continue
        gold.sort(key=lambda m: -m['size'])
        s = (comp / 100 * laps) % 1
        bins[min(num_bins - 1, int(s * num_bins))].append((gold[0]['x'], gold[0]['y']))

    center = []
    for i, b in enumerate(bins):
        if b:
            xs = sorted(p[0] for p in b)
            ys = sorted(p[1] for p in b)
            center.append({'s': i / num_bins, 'x': xs[len(xs) // 2], 'y': ys[len(ys) // 2]})
    return center


class TrackMap:
    """Arc-length model of a single track."""

    def __init__(self, centerline):
        # centerline: ordered list of {s, x, y}, s ascending in [0,1)
        self.pts = centerline
        # Cumulative real arc length (in pixels) at each centerline point,
        # so gaps can be reported in pixels as well as lap fraction.
        self.cum = [0.0]
        for i in range(1, len(self.pts) + 1):
            a = self.pts[i - 1]
            b = self.pts[i % len(self.pts)]
            self.cum.append(self.cum[-1] + math.hypot(b['x'] - a['x'], b['y'] - a['y']))
        self.length_px = self.cum[-1]  # full lap length in pixels

    def project(self, x, y):
        """Return the lap fraction s in [0,1) closest to pixel (x, y)."""
        best_s, best_d = 0.0, float('inf')
        for p in self.pts:
            d = (x - p['x']) ** 2 + (y - p['y']) ** 2
            if d < best_d:
                best_d, best_s = d, p['s']
        return best_s

    def gap_laps(self, s_ahead, s_behind):
        """Forward arc distance from the trailing car to the leading car,
        as a fraction of one lap (0..1). Handles wrap-around."""
        return (s_ahead - s_behind) % 1.0

    def gap_px(self, s_ahead, s_behind):
        """Same gap, expressed in track pixels (real distance along the road)."""
        return self.gap_laps(s_ahead, s_behind) * self.length_px


def _demo(session_path):
    """Build the map and print inter-car gaps for the last few frames."""
    center = build_centerline(session_path)
    tm = TrackMap(center)
    print(f"Centerline: {len(center)} points, lap length {tm.length_px:.0f} px\n")

    lines = [l for l in Path(session_path).read_text(encoding='utf-8', errors='replace').split('\n') if l.strip()]
    frames = [json.loads(l) for l in lines if json.loads(l).get('type') == 'race_state']

    for ev in frames[-3:]:
        d = ev['data']
        laps = d.get('laps') or 1
        drivers = d['drivers']
        print(f"{d['track']}  ({d['status']})")
        # s from completion (precise) for each driver
        rows = []
        for dr in drivers:
            s = (dr['completion'] / 100 * laps) % 1
            rows.append((dr['position'], dr['name'], dr['completion'], s))
        # gaps to the leader, along the track
        leader_s = rows[0][3]
        for pos, name, comp, s in rows:
            gap_l = tm.gap_laps(leader_s, s)
            gap_p = tm.gap_px(leader_s, s)
            tag = 'LEADER' if pos == 1 else f"-{gap_l*100:5.2f}% lap  (~{gap_p:5.0f} px behind)"
            print(f"  P{pos} {name:<12} {comp:6.2f}%   {tag}")
        print()


if __name__ == '__main__':
    import sys
    session = sys.argv[1] if len(sys.argv) > 1 else 'spy_results/session_20260603_064437.jsonl'
    _demo(session)
