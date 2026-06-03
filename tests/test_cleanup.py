"""Tests for cleanup.py — keeps the N most recent files per category."""

import os
import time

from cleanup import cleanup


def _make(dirpath, name, age_seconds):
    p = dirpath / name
    p.write_text("x")
    t = time.time() - age_seconds
    os.utime(p, (t, t))   # set mtime so "most recent" ordering is deterministic
    return p


def test_keeps_two_most_recent_per_type(tmp_path):
    # three races' worth of files, oldest → newest by mtime
    for i, age in enumerate([300, 200, 100]):
        _make(tmp_path, f"session_{i}.jsonl", age)
        _make(tmp_path, f"events_{i}.jsonl", age)
        _make(tmp_path, f"commentary_{i}.txt", age)
        _make(tmp_path, f"commentary_{i}.jsonl", age)

    removed = cleanup(keep=2, out_dir=tmp_path)

    # only the oldest (index 0) of each of the 4 types should be gone
    assert sorted(removed) == sorted([
        "session_0.jsonl", "events_0.jsonl",
        "commentary_0.txt", "commentary_0.jsonl",
    ])
    remaining = {p.name for p in tmp_path.iterdir()}
    assert "session_0.jsonl" not in remaining
    assert "session_1.jsonl" in remaining
    assert "session_2.jsonl" in remaining


def test_keep_one(tmp_path):
    _make(tmp_path, "session_a.jsonl", 200)
    _make(tmp_path, "session_b.jsonl", 100)
    removed = cleanup(keep=1, out_dir=tmp_path)
    assert removed == ["session_a.jsonl"]
    assert {p.name for p in tmp_path.iterdir()} == {"session_b.jsonl"}


def test_track_artifacts_never_touched(tmp_path):
    _make(tmp_path, "track_A5_centerline.json", 500)
    _make(tmp_path, "centerline_from_cars.png", 500)
    _make(tmp_path, "session_a.jsonl", 200)
    _make(tmp_path, "session_b.jsonl", 100)
    cleanup(keep=1, out_dir=tmp_path)
    remaining = {p.name for p in tmp_path.iterdir()}
    assert "track_A5_centerline.json" in remaining
    assert "centerline_from_cars.png" in remaining


def test_dry_run_deletes_nothing(tmp_path):
    _make(tmp_path, "session_a.jsonl", 200)
    _make(tmp_path, "session_b.jsonl", 100)
    removed = cleanup(keep=1, dry_run=True, out_dir=tmp_path)
    assert removed == ["session_a.jsonl"]
    # nothing actually deleted
    assert {p.name for p in tmp_path.iterdir()} == {"session_a.jsonl", "session_b.jsonl"}


def test_nothing_to_remove(tmp_path):
    _make(tmp_path, "session_a.jsonl", 100)
    assert cleanup(keep=2, out_dir=tmp_path) == []
