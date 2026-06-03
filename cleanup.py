#!/usr/bin/env python3
"""
Keep only the most recent races' data in spy_results/.

Each run of the software (= one race) produces a set of timestamped files:
  session_<stamp>.jsonl, events_<stamp>.jsonl,
  commentary_<stamp>.txt, commentary_<stamp>.jsonl

This trims each category to the N most recent files (default 2 → current race +
previous race). Reusable track artifacts (track_*, centerline_*) are never touched.

Usage:
  python cleanup.py                 # keep the 2 most recent races
  python cleanup.py --keep 1        # keep only the most recent race
  python cleanup.py --dry-run       # show what would be deleted, delete nothing
"""

import argparse
from pathlib import Path

OUT_DIR = Path("spy_results")

# Per-race data files (timestamped). Track artifacts are intentionally excluded.
PATTERNS = [
    "session_*.jsonl",
    "events_*.jsonl",
    "commentary_*.txt",
    "commentary_*.jsonl",
]


def cleanup(keep=2, dry_run=False, out_dir=OUT_DIR):
    """Delete all but the `keep` most recent files of each per-race category.
    Returns the list of removed file names."""
    removed = []
    for pattern in PATTERNS:
        files = sorted(out_dir.glob(pattern),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[keep:]:
            removed.append(f.name)
            if not dry_run:
                f.unlink()
    return removed


def main():
    ap = argparse.ArgumentParser(description="Trim old race data in spy_results/")
    ap.add_argument("--keep", type=int, default=2,
                    help="races to keep (default 2: current + previous)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be removed without deleting")
    args = ap.parse_args()

    if not OUT_DIR.exists():
        print(f"  {OUT_DIR}/ does not exist — nothing to clean.")
        return

    removed = cleanup(args.keep, args.dry_run)
    verb = "Would remove" if args.dry_run else "Removed"
    print(f"  {verb} {len(removed)} old file(s); kept {args.keep} most recent per type.")
    for name in removed:
        print(f"    - {name}")


if __name__ == "__main__":
    main()
