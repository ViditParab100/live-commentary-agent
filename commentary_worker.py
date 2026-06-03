#!/usr/bin/env python3
"""
Commentary worker — consumes race events and produces live AI commentary.

It is intentionally DECOUPLED from the HTTP listener: the listener stays fast
(receive → persist → display) while this separate process does the slow work
(calling Claude). They share the events_*.jsonl file.

Modes
-----
  python commentary_worker.py                       # tail newest events_*.jsonl (live)
  python commentary_worker.py --events <file>       # tail a specific events file
  python commentary_worker.py --replay <session>    # replay a raw session through the detector
  python commentary_worker.py --replay <s> --speed 5  # 5x faster replay

Options
-------
  --min-priority N   only commentate events with priority >= N (default 3)
  --model NAME       Claude model id (default: fast Haiku for live latency)
  --dry-run          don't call Claude; print the prompt that WOULD be sent.
                     Auto-enabled when ANTHROPIC_API_KEY is missing, so the whole
                     pipeline is testable with no key and no cost.

Replay is the key testing tool: pipe any saved race through the exact live
commentary path without needing a real race.
"""

import argparse
import json
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from event_detector import EventDetector

# Force UTF-8 stdout on Windows so any characters print cleanly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Fast model keeps live commentary punchy and cheap across many events.
# Override with --model claude-sonnet-4-6 for richer lines.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

OUT_DIR = Path("spy_results")

# The commentator persona — sent as a cached system prompt so repeated calls
# across the race hit the prompt cache instead of re-billing these tokens.
SYSTEM_PROMPT = (
    "You are an energetic live motorsport commentator for Torn City street races. "
    "You receive a stream of race events. For each NEW event, deliver ONE short, "
    "punchy line of commentary (max 2 sentences) as if broadcasting live. "
    "Be vivid and specific, use the driver names, and react to the moment. "
    "Do not repeat yourself, do not add quotation marks, do not narrate that you "
    "are an AI. Vary your phrasing across calls."
)


# --------------------------------------------------------------------------
# Event sources
# --------------------------------------------------------------------------
def latest_events_file():
    files = sorted(OUT_DIR.glob("events_*.jsonl"))
    return files[-1] if files else None


def tail_events(path, from_start=False, poll=0.3):
    """Yield event dicts from a JSONL file as they are appended."""
    path = Path(path)
    while not path.exists():
        print(f"  (waiting for {path} ...)", flush=True)
        time.sleep(0.5)
    with open(path, "r", encoding="utf-8") as f:
        if not from_start:
            f.seek(0, 2)  # jump to end → only new events
        while True:
            line = f.readline()
            if not line:
                time.sleep(poll)
                continue
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass


def replay_session(path, speed=10.0):
    """Replay a raw session JSONL through the detector, yielding events.
    Sleeps between frames by their real time gap divided by `speed`."""
    det = EventDetector()
    lines = [l for l in Path(path).read_text(encoding="utf-8", errors="replace").split("\n") if l.strip()]
    prev_ts = None
    for l in lines:
        frame = json.loads(l)
        if frame.get("type") != "race_state":
            continue
        ts = frame.get("ts", 0) / 1000.0
        if prev_ts is not None and speed > 0:
            time.sleep(min(2.0, max(0.0, (ts - prev_ts) / speed)))
        prev_ts = ts
        for e in det.process(frame):
            yield e


# --------------------------------------------------------------------------
# Commentator
# --------------------------------------------------------------------------
class Commentator:
    """Provider-agnostic commentary generator.

    Backend selection (first available wins):
      SARVAM_API_KEY    -> Sarvam (OpenAI-compatible; reasoning model, ~slow)
      ANTHROPIC_API_KEY -> Claude (streaming, fast)
      neither           -> dry-run (prints prompts)
    """

    SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"

    def __init__(self, model=None, dry_run=False, log_path=None, jsonl_path=None):
        self.recent = deque(maxlen=6)
        self.backend = "dry"
        self.model = model
        self._client = None
        self.log_path = log_path       # human-readable .txt
        self.jsonl_path = jsonl_path   # structured .jsonl (for Discord etc.)

        if dry_run:
            return
        if os.getenv("SARVAM_API_KEY"):
            self.backend = "sarvam"
            self.model = model or "sarvam-30b"
            self._key = os.getenv("SARVAM_API_KEY")
        elif os.getenv("ANTHROPIC_API_KEY"):
            self.backend = "anthropic"
            self.model = model or "claude-haiku-4-5-20251001"
            import anthropic
            self._client = anthropic.Anthropic()

    def _user_prompt(self, event):
        recent = "\n".join(f"- {m}" for m in self.recent) or "- (race just beginning)"
        return (
            f"Recent events:\n{recent}\n\n"
            f"NEW EVENT (priority {event['priority']}, {event['type']}):\n"
            f"{event['message']}\n\n"
            f"Give ONE line of live commentary for this moment."
        )

    # --- backends ---------------------------------------------------------
    def _sarvam(self, prompt):
        import requests
        payload = {
            "model": self.model,
            "reasoning_effort": "low",
            "max_tokens": 3000,           # reasoning models need headroom to FINISH
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        r = requests.post(self.SARVAM_URL,
                          headers={"Authorization": f"Bearer {self._key}",
                                   "Content-Type": "application/json"},
                          json=payload, timeout=90)
        data = r.json()
        if "choices" not in data:
            return f"(sarvam error: {data.get('error', {}).get('message', r.text[:120])})"
        text = (data["choices"][0]["message"].get("content") or "").strip()
        if not text:
            text = "(model still thinking — increase max_tokens)"
        return text

    def _anthropic(self, prompt):
        out = []
        with self._client.messages.stream(
            model=self.model, max_tokens=120,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                out.append(text)
        return "".join(out).strip()

    # --- public -----------------------------------------------------------
    def say(self, event):
        prompt = self._user_prompt(event)
        self.recent.append(event["message"])

        if self.backend == "dry":
            print(f"\n[would-commentate P{event['priority']} {event['type']}]")
            print(f"  event : {event['message']}")
            return

        t0 = time.time()
        try:
            text = self._sarvam(prompt) if self.backend == "sarvam" else self._anthropic(prompt)
        except Exception as e:
            # A single API timeout/error must never kill the long-running worker.
            print(f"\n  [commentary skipped — {type(e).__name__}: {e}]", flush=True)
            return
        dt = time.time() - t0
        clock = datetime.fromtimestamp(event["ts"]).strftime("%H:%M:%S")
        line = f"[{clock}] {event['type']} (+{dt:.0f}s)  {text}"
        print(f"\n>> {line}", flush=True)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.jsonl_path:
            rec = {"ts": event["ts"], "time": clock, "type": event["type"],
                   "priority": event["priority"], "text": text,
                   "latency_s": round(dt, 1)}
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Live AI commentary worker")
    ap.add_argument("--events", help="specific events_*.jsonl to tail")
    ap.add_argument("--replay", help="replay a raw session_*.jsonl through the detector")
    ap.add_argument("--speed", type=float, default=10.0, help="replay speed multiplier")
    ap.add_argument("--min-priority", type=int, default=3, help="min event priority to consider")
    ap.add_argument("--interval", type=float, default=60.0,
                    help="seconds between filler lines (steady cadence). 0 = voice every event.")
    ap.add_argument("--model", default=None,
                    help="override model id (else each backend picks its own default)")
    ap.add_argument("--from-start", action="store_true", help="tail from start of events file")
    ap.add_argument("--dry-run", action="store_true", help="print prompts instead of calling Claude")
    args = ap.parse_args()

    # Load .env for ANTHROPIC_API_KEY if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    has_key = os.getenv("SARVAM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    dry = args.dry_run or not has_key
    if dry and not args.dry_run:
        print("  [no SARVAM_API_KEY / ANTHROPIC_API_KEY found → running in --dry-run mode]\n")

    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path   = OUT_DIR / f"commentary_{stamp}.txt"
    jsonl_path = OUT_DIR / f"commentary_{stamp}.jsonl"
    comm = Commentator(model=args.model, dry_run=dry, log_path=log_path, jsonl_path=jsonl_path)
    # Create the logs immediately so they can be opened and watched live.
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# Live commentary — backend={comm.backend} model={comm.model}\n")
        f.write(f"# started {datetime.now().isoformat(timespec='seconds')}\n\n")
    jsonl_path.touch()
    if not dry:
        print(f"  Backend: {comm.backend}  (model: {comm.model})")
    print(f"  Commentary log: {log_path.resolve()}")
    print(f"  Structured    : {jsonl_path.resolve()}\n")

    # Choose event source
    if args.replay:
        print(f"  Replaying {args.replay} at {args.speed}x  (min priority {args.min_priority})\n")
        source = replay_session(args.replay, args.speed)
    else:
        path = args.events or latest_events_file()
        if not path:
            print("  No events file found. Start ws_listener.py and a race first,")
            print("  or use --replay <session_*.jsonl> to test on a saved race.")
            return
        print(f"  Tailing {path}  (min priority {args.min_priority})\n")
        source = tail_events(path, from_start=args.from_start)

    print(f"  Cadence: one filler line per {args.interval:.0f}s; P5 events voiced immediately.\n")

    voiced = 0
    buffer = []          # candidate events waiting to be voiced
    last_voiced_ts = 0.0
    IMMEDIATE = 5        # priority >= this is voiced at once (lead change, finish)

    def pick(events):
        # highest priority, then most recent
        return sorted(events, key=lambda e: (e['priority'], e['ts']))[-1]

    try:
        for event in source:
            if event.get("priority", 0) < args.min_priority:
                continue
            ts = event.get("ts", 0)

            # Big moments jump the queue and reset the cadence clock.
            if event["priority"] >= IMMEDIATE:
                comm.say(event)
                voiced += 1
                buffer.clear()
                last_voiced_ts = ts
                continue

            buffer.append(event)

            # Otherwise voice the best buffered event once per interval.
            if args.interval <= 0 or (ts - last_voiced_ts) >= args.interval:
                comm.say(pick(buffer))
                voiced += 1
                buffer.clear()
                last_voiced_ts = ts
    except KeyboardInterrupt:
        pass
    print(f"\n  {voiced} lines of commentary generated.")


if __name__ == "__main__":
    main()
