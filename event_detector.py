#!/usr/bin/env python3
"""
Event detector — turns a stream of race_state frames into discrete race events
worth commentating on (overtakes, lead changes, closing battles, final lap,
finish, etc.).

Designed to run both:
  - offline:  replay a session JSONL  ->  python event_detector.py <session>
  - online:   feed live frames from ws_listener one at a time via .process()

Each event is a dict:
  { ts, type, priority, message, data }

priority: 1 (minor) .. 5 (must-say). The commentary engine (Phase 3) can use
this to decide what to voice and how urgently.
"""

import json
import sys
from collections import deque
from pathlib import Path


# --- tunables -------------------------------------------------------------
BATTLE_LAP   = 0.03    # cars within 3% of a lap = a battle
CLOSE_WINDOW = 6.0     # seconds of history used for trend detection
CLOSE_DROP   = 0.015   # gap must shrink this many laps over the window to be "closing"
CLOSE_RANGE  = 0.20    # only call closing when within 20% of a lap
COOLDOWN     = 8.0     # seconds before the same (type, pair) can fire again
TICK_INTERVAL = 45.0   # seconds between periodic race-update heartbeats


def gap_laps(comp_ahead, comp_behind, laps):
    """Along-track gap as a fraction of one lap (ahead − behind)."""
    return (comp_ahead - comp_behind) / 100.0 * laps


class EventDetector:
    def __init__(self):
        self.prev_pos   = {}       # name -> position (previous frame)
        self.gap_hist   = {}       # (ahead, behind) -> deque[(ts, gap)]
        self.cooldowns  = {}       # (type, key) -> last_ts
        self.started    = False
        self.final_lap  = False
        self.finished   = False
        self.last_leader = None
        self.last_tick  = None     # ts of last periodic race-update heartbeat
        self.prev_comp  = {}       # name -> completion last frame (new-race detection)

    def _reset_for_new_race(self):
        """A new race started (completions reset). Clear per-race state so the
        next frames are treated as a fresh race rather than computing nonsense
        gaps across the race boundary."""
        self.prev_pos = {}
        self.gap_hist = {}
        self.cooldowns = {}
        self.started = False
        self.final_lap = False
        self.finished = False
        self.last_tick = None
        self.last_leader = None

    # -- cooldown helper ----------------------------------------------------
    def _ready(self, etype, key, ts):
        last = self.cooldowns.get((etype, key), -1e9)
        if ts - last >= COOLDOWN:
            self.cooldowns[(etype, key)] = ts
            return True
        return False

    # -- main entry ---------------------------------------------------------
    def process(self, frame):
        """Feed one race_state event dict; returns a list of detected events."""
        d = frame.get('data', frame)
        ts = frame.get('ts', d.get('ts', 0)) / 1000.0
        drivers = d.get('drivers') or []
        if not drivers:
            return []
        laps = d.get('laps') or 1
        track = d.get('track', '?')
        status = d.get('status', '')
        events = []

        # sort by position (leader first)
        drivers = sorted(drivers, key=lambda x: x['position'])
        cur_pos = {dr['name']: dr['position'] for dr in drivers}
        comp = {dr['name']: dr['completion'] for dr in drivers}

        def emit(etype, priority, message, **data):
            events.append({'ts': ts, 'type': etype, 'priority': priority,
                           'message': message, 'data': data})

        # --- new-race / finish boundary detection ---
        # completion only ever rises within a race; if ANY driver's completion
        # drops, that driver finished and reset for the next race. The frame is
        # then a mix of old- and new-race values, so skip it entirely to avoid
        # garbage gaps (the "8 laps behind" bug), and reset for the new race.
        boundary = any(comp[n] < self.prev_comp.get(n, -1) - 5 for n in comp)
        self.prev_comp = dict(comp)
        if boundary:
            self._reset_for_new_race()
            return events  # nothing trustworthy to say on a boundary frame

        # --- race start (first active frame) ---
        # Trigger on active racing, not the status string: the status reflects the
        # PLAYER's state ("Race started", but also "You crashed!", etc.) and would
        # otherwise leave `started` False and suppress the heartbeat for the race.
        racing_active = any(0 < comp[dr['name']] < 100 for dr in drivers)
        if not self.started and not self.finished and racing_active:
            self.started = True
            names = ', '.join(dr['name'] for dr in drivers)
            emit('race_start', 4, f"And they're off at {track}! {len(drivers)} drivers: {names}.",
                 track=track, laps=laps)

        # --- position changes / overtakes (vs previous frame) ---
        if self.prev_pos:
            for dr in drivers:
                name, pos = dr['name'], dr['position']
                old = self.prev_pos.get(name)
                if old is not None and pos < old:
                    # moved up — find who they passed (now directly behind, was ahead)
                    passed = [n for n, p in cur_pos.items()
                              if p == pos + 1 and self.prev_pos.get(n, 99) <= old and n != name]
                    who = passed[0] if passed else None
                    if pos == 1:
                        if self._ready('lead_change', name, ts):
                            tail = f" from {who}" if who else ""
                            emit('lead_change', 5, f"Lead change! {name} takes P1{tail} at {track}.",
                                 driver=name, passed=who)
                    else:
                        if self._ready('overtake', name, ts):
                            tail = f" past {who}" if who else ""
                            emit('overtake', 4, f"{name} moves up to P{pos}{tail}.",
                                 driver=name, position=pos, passed=who)

        # --- adjacent-pair gap analysis: battles, closing, pulling away ---
        for i in range(len(drivers) - 1):
            ahead, behind = drivers[i], drivers[i + 1]
            key = (ahead['name'], behind['name'])
            g = gap_laps(comp[ahead['name']], comp[behind['name']], laps)

            hist = self.gap_hist.setdefault(key, deque())
            hist.append((ts, g))
            while hist and ts - hist[0][0] > CLOSE_WINDOW:
                hist.popleft()

            # battle: very tight gap
            if 0 <= g <= BATTLE_LAP and self._ready('battle', key, ts):
                emit('battle', 4,
                     f"{behind['name']} is right on {ahead['name']}'s tail for P{ahead['position']} "
                     f"— just {g*100:.1f}% of a lap between them!",
                     ahead=ahead['name'], behind=behind['name'], gap=g)

            # closing: gap shrank meaningfully over the window
            elif len(hist) >= 2 and g <= CLOSE_RANGE:
                drop = hist[0][1] - g
                if drop >= CLOSE_DROP and self._ready('closing', key, ts):
                    emit('closing', 3,
                         f"{behind['name']} is reeling in {ahead['name']} — gap down to "
                         f"{g*100:.1f}% of a lap.",
                         ahead=ahead['name'], behind=behind['name'], gap=g, drop=drop)

        # --- final lap (based on the leader) ---
        leader = drivers[0]
        leader_lap = int(comp[leader['name']] / 100 * laps) + 1
        if not self.final_lap and leader_lap >= laps and laps > 1:
            self.final_lap = True
            emit('final_lap', 5, f"Final lap! {leader['name']} leads onto the last lap at {track}.",
                 leader=leader['name'])

        # --- finish ---
        if not self.finished and ('finish' in status.lower() or 'ended' in status.lower()):
            self.finished = True
            order = ', '.join(f"P{dr['position']} {dr['name']}" for dr in drivers)
            emit('race_finished', 5, f"Chequered flag at {track}! Final order: {order}.",
                 order=[dr['name'] for dr in drivers])

        # --- periodic race-update heartbeat (keeps commentary flowing in lulls) ---
        if self.started and not self.finished:
            if self.last_tick is None:
                self.last_tick = ts
            elif ts - self.last_tick >= TICK_INTERVAL:
                self.last_tick = ts
                parts = []
                for dr in drivers[1:]:
                    g = gap_laps(comp[leader['name']], comp[dr['name']], laps)
                    parts.append(f"{dr['name']} {g*100:.0f}% of a lap back")
                gaps = "; ".join(parts) if parts else "leading unchallenged"
                emit('race_update', 3,
                     f"Lap {leader_lap} of {laps} at {track}: {leader['name']} leads, {gaps}.",
                     leader=leader['name'], lap=leader_lap)

        self.prev_pos = cur_pos
        self.last_leader = leader['name']
        return events


def _replay(session_path):
    lines = [l for l in Path(session_path).read_text(encoding='utf-8', errors='replace').split('\n') if l.strip()]
    det = EventDetector()
    total = 0
    for l in lines:
        ev = json.loads(l)
        if ev.get('type') != 'race_state':
            continue
        for out in det.process(ev):
            total += 1
            from datetime import datetime
            t = datetime.fromtimestamp(out['ts']).strftime('%H:%M:%S')
            stars = '*' * out['priority']
            print(f"[{t}] P{out['priority']} {out['type']:<14} {out['message']}")
    print(f"\n{total} events detected.")


if __name__ == '__main__':
    session = sys.argv[1] if len(sys.argv) > 1 else 'spy_results/session_20260603_064437.jsonl'
    _replay(session)
