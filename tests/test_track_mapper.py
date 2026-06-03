"""Tests for track_mapper.py"""

import json

import pytest

from track_mapper import TrackMap, build_centerline


# A simple square loop: 4 corners, each side 10 px → lap length 40 px.
SQUARE = [
    {'s': 0.00, 'x': 0,  'y': 0},
    {'s': 0.25, 'x': 10, 'y': 0},
    {'s': 0.50, 'x': 10, 'y': 10},
    {'s': 0.75, 'x': 0,  'y': 10},
]


# --- TrackMap.length ------------------------------------------------------
def test_lap_length_px():
    tm = TrackMap(SQUARE)
    assert tm.length_px == pytest.approx(40.0)


# --- project --------------------------------------------------------------
def test_project_exact_corner():
    tm = TrackMap(SQUARE)
    assert tm.project(10, 0) == 0.25
    assert tm.project(0, 10) == 0.75

def test_project_nearest():
    tm = TrackMap(SQUARE)
    # (9, 1) is closest to corner (10, 0) at s=0.25
    assert tm.project(9, 1) == 0.25


# --- gap_laps (wrap-around) ----------------------------------------------
def test_gap_forward():
    tm = TrackMap(SQUARE)
    assert tm.gap_laps(0.50, 0.25) == pytest.approx(0.25)

def test_gap_wraparound():
    tm = TrackMap(SQUARE)
    # leader at 0.10, trailer at 0.90 → leader is 0.20 ahead (wraps past 0)
    assert tm.gap_laps(0.10, 0.90) == pytest.approx(0.20)

def test_gap_zero_when_same():
    tm = TrackMap(SQUARE)
    assert tm.gap_laps(0.4, 0.4) == 0.0


# --- gap_px ---------------------------------------------------------------
def test_gap_px_conversion():
    tm = TrackMap(SQUARE)
    # 0.25 lap of a 40 px lap = 10 px
    assert tm.gap_px(0.50, 0.25) == pytest.approx(10.0)


# --- build_centerline -----------------------------------------------------
def test_build_centerline_orders_by_lap_fraction(tmp_path):
    # Synthetic session: laps=1 so lap_fraction == completion/100.
    # Player gold marker moves along x = round(completion), y = 50.
    session = tmp_path / "synthetic.jsonl"
    rows = []
    for i in range(100):                      # completion 0.0 .. 99.0
        comp = float(i)
        rows.append(json.dumps({
            'type': 'race_state',
            'ts': 1000 + i,
            'data': {
                'track': 'Syn', 'laps': 1, 'status': 'Race started',
                'drivers': [{'position': 1, 'name': 'Me', 'completion': comp}],
                'my_info': {'name': 'Me', 'completion': comp},
                'canvas_markers': {
                    'w': 200, 'h': 100,
                    'markers': [{'x': i, 'y': 50, 'r': 190, 'g': 150, 'b': 40, 'size': 8}],
                },
            },
        }))
    session.write_text('\n'.join(rows))

    center = build_centerline(str(session), num_bins=20)
    assert len(center) > 0
    # s must be strictly increasing and x must rise with s (path is ordered)
    ss = [p['s'] for p in center]
    xs = [p['x'] for p in center]
    assert ss == sorted(ss)
    assert xs == sorted(xs)


def test_build_centerline_ignores_non_gold_markers(tmp_path):
    # Only a red marker present → no gold trail → empty centerline.
    session = tmp_path / "red_only.jsonl"
    rows = []
    for i in range(10):
        rows.append(json.dumps({
            'type': 'race_state', 'ts': 1000 + i,
            'data': {
                'track': 'Syn', 'laps': 1, 'status': 'Race started',
                'drivers': [{'position': 1, 'name': 'Me', 'completion': float(i)}],
                'my_info': {'name': 'Me', 'completion': float(i)},
                'canvas_markers': {'w': 200, 'h': 100,
                                   'markers': [{'x': i, 'y': 50, 'r': 190, 'g': 40, 'b': 40, 'size': 8}]},
            },
        }))
    session.write_text('\n'.join(rows))
    assert build_centerline(str(session)) == []
