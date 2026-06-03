#!/usr/bin/env python3
"""
Discord output for the commentary pipeline.

Posts commentary lines to a Discord channel using plain HTTPS (the `requests`
library) — no async `discord.py` gateway needed, so it drops cleanly into the
synchronous commentary worker.

Two backends, auto-selected (webhook wins if both are set):
  DISCORD_WEBHOOK_URL                      -> post via channel webhook (simplest)
  DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID   -> post as a bot via the REST API

Standalone use (decoupled): tail a commentary jsonl and post each new line:
  python discord_notify.py --jsonl spy_results/commentary_<stamp>.jsonl
"""

import json
import os
import time
from pathlib import Path

import requests

DISCORD_API = "https://discord.com/api/v10"

EVENT_EMOJI = {
    "race_start":    "🚦",
    "lead_change":   "🔄",
    "overtake":      "⏫",
    "battle":        "⚔️",
    "closing":       "📈",
    "final_lap":     "🔔",
    "race_finished": "🏁",
}


class DiscordNotifier:
    """Synchronous Discord poster. .enabled is False if no creds are configured."""

    def __init__(self):
        self.webhook = os.getenv("DISCORD_WEBHOOK_URL")
        self.token = os.getenv("DISCORD_BOT_TOKEN")
        self.channel = os.getenv("DISCORD_CHANNEL_ID")
        if self.webhook:
            self.mode = "webhook"
        elif self.token and self.channel:
            self.mode = "bot"
        else:
            self.mode = None

    @property
    def enabled(self):
        return self.mode is not None

    def format(self, text, event_type=None, clock=None):
        emoji = EVENT_EMOJI.get(event_type, "🎙️")
        prefix = f"{emoji} "
        if clock:
            prefix += f"`[{clock}]` "
        return f"{prefix}{text}"

    def post(self, text, event_type=None, clock=None):
        """Post one message. Never raises — Discord problems must not break
        commentary generation; failures are returned as False."""
        if not self.enabled:
            return False
        content = self.format(text, event_type, clock)
        try:
            if self.mode == "webhook":
                r = requests.post(self.webhook, json={"content": content}, timeout=10)
            else:
                r = requests.post(
                    f"{DISCORD_API}/channels/{self.channel}/messages",
                    headers={"Authorization": f"Bot {self.token}"},
                    json={"content": content}, timeout=10,
                )
            if r.status_code == 429:  # rate limited — respect retry_after
                time.sleep(float(r.json().get("retry_after", 1.0)))
                return self.post(text, event_type, clock)
            return r.status_code < 300
        except Exception as e:
            print(f"  [discord post failed: {type(e).__name__}: {e}]")
            return False


def _tail_and_post(jsonl_path, from_start=False):
    """Standalone: tail a commentary jsonl and post each line to Discord."""
    notifier = DiscordNotifier()
    if not notifier.enabled:
        print("  No Discord creds found. Set DISCORD_WEBHOOK_URL, or "
              "DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID in .env.")
        return
    print(f"  Discord mode: {notifier.mode}.  Tailing {jsonl_path}")

    path = Path(jsonl_path)
    while not path.exists():
        time.sleep(0.5)
    with open(path, "r", encoding="utf-8") as f:
        if not from_start:
            f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ok = notifier.post(rec.get("text", ""), rec.get("type"), rec.get("time"))
            print(f"  -> discord {'ok' if ok else 'FAILED'}: {rec.get('text','')[:60]}")


if __name__ == "__main__":
    import argparse
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    ap = argparse.ArgumentParser(description="Post commentary jsonl to Discord")
    ap.add_argument("--jsonl", required=True, help="commentary_*.jsonl to tail")
    ap.add_argument("--from-start", action="store_true")
    args = ap.parse_args()
    _tail_and_post(args.jsonl, args.from_start)
