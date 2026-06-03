"""Tests for event_detector.py"""

import pytest

from event_detector import EventDetector, gap_laps


# --- helpers --------------------------------------------------------------
def driver(pos, name, comp):
    return {'position': pos, 'name': name, 'completion': comp}

def frame(drivers, ts_ms, laps=10, status='Race started', track='Test', my=None):
    return {
        'type': 'race_state',
        'ts': ts_ms,
        'data': {
            'track': track, 'laps': laps, 'status': status,
            'drivers': drivers, 'my_info': my or {},
        },
    }

def types(events):
    return [e['type'] for e in events]


# --- gap_laps -------------------------------------------------------------
def test_gap_laps_basic():
    # 1% of race difference over a 10-lap race = 0.1 lap
    assert gap_laps(50.0, 49.0, 10) == pytest.approx(0.1)

def test_gap_laps_zero():
    assert gap_laps(50.0, 50.0, 10) == 0.0


# --- race start -----------------------------------------------------------
def test_race_start_emitted_once():
    det = EventDetector()
    e1 = det.process(frame([driver(1, 'A', 5), driver(2, 'B', 4)], 1000))
    assert 'race_start' in types(e1)
    # second frame must not re-emit the start
    e2 = det.process(frame([driver(1, 'A', 6), driver(2, 'B', 5)], 2000))
    assert 'race_start' not in types(e2)


# --- overtake -------------------------------------------------------------
def test_overtake_detected():
    det = EventDetector()
    det.process(frame([driver(1, 'A', 50), driver(2, 'B', 40), driver(3, 'C', 30)], 1000))
    # C jumps from P3 to P2, passing B
    evs = det.process(frame([driver(1, 'A', 51), driver(2, 'C', 45), driver(3, 'B', 44)], 2000))
    ot = [e for e in evs if e['type'] == 'overtake']
    assert ot, "expected an overtake event"
    assert ot[0]['data']['driver'] == 'C'
    assert ot[0]['data']['passed'] == 'B'


# --- lead change ----------------------------------------------------------
def test_lead_change_detected():
    det = EventDetector()
    det.process(frame([driver(1, 'A', 50), driver(2, 'B', 49)], 1000))
    evs = det.process(frame([driver(1, 'B', 51), driver(2, 'A', 50)], 2000))
    lc = [e for e in evs if e['type'] == 'lead_change']
    assert lc, "expected a lead_change event"
    assert lc[0]['priority'] == 5
    assert lc[0]['data']['driver'] == 'B'


# --- battle ---------------------------------------------------------------
def test_battle_when_cars_tight():
    det = EventDetector()
    # gap = (50.2 - 50.0)/100 * 10 = 0.02 lap < BATTLE_LAP (0.03)
    evs = det.process(frame([driver(1, 'A', 50.2), driver(2, 'B', 50.0)], 1000))
    assert 'battle' in types(evs)


def test_no_battle_when_far():
    det = EventDetector()
    # gap = (55 - 50)/100 * 10 = 0.5 lap — far apart
    evs = det.process(frame([driver(1, 'A', 55), driver(2, 'B', 50)], 1000))
    assert 'battle' not in types(evs)


# --- closing --------------------------------------------------------------
def test_closing_detected_over_window():
    det = EventDetector()
    # frame1: gap 0.2 lap (within CLOSE_RANGE, no event yet — only 1 sample)
    det.process(frame([driver(1, 'A', 55), driver(2, 'B', 53)], 1000))
    # frame2: gap shrinks to 0.1 lap → drop 0.1 >= CLOSE_DROP
    evs = det.process(frame([driver(1, 'A', 55), driver(2, 'B', 54)], 3000))
    assert 'closing' in types(evs)


# --- final lap ------------------------------------------------------------
def test_final_lap_detected_once():
    det = EventDetector()
    # laps=10, leader comp 92 → leader_lap = int(9.2)+1 = 10 = final lap
    e1 = det.process(frame([driver(1, 'A', 92), driver(2, 'B', 90)], 1000, laps=10))
    assert 'final_lap' in types(e1)
    e2 = det.process(frame([driver(1, 'A', 93), driver(2, 'B', 91)], 2000, laps=10))
    assert 'final_lap' not in types(e2)


# --- finish ---------------------------------------------------------------
def test_race_finished_detected():
    det = EventDetector()
    det.process(frame([driver(1, 'A', 99), driver(2, 'B', 98)], 1000))
    evs = det.process(frame([driver(1, 'A', 100), driver(2, 'B', 99)], 2000, status='Race finished'))
    fin = [e for e in evs if e['type'] == 'race_finished']
    assert fin, "expected a race_finished event"
    assert fin[0]['data']['order'] == ['A', 'B']


# --- cooldown -------------------------------------------------------------
def test_battle_cooldown_suppresses_repeats():
    det = EventDetector()
    tight = lambda ts: frame([driver(1, 'A', 50.2), driver(2, 'B', 50.0)], ts)
    e1 = det.process(tight(1000))
    e2 = det.process(tight(2000))    # 1s later — within 8s cooldown
    assert 'battle' in types(e1)
    assert 'battle' not in types(e2)
    e3 = det.process(tight(11000))   # 10s after first — cooldown expired
    assert 'battle' in types(e3)


# --- robustness -----------------------------------------------------------
def test_empty_drivers_no_crash():
    det = EventDetector()
    assert det.process(frame([], 1000)) == []
