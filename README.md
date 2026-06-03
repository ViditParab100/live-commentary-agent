# Live Commentary Agent

AI-powered live race commentary for **Torn City Racing**. It captures a live race from the browser, detects the dramatic moments, generates broadcast-style commentary with an LLM, and posts it to Discord.

---

## Pipeline

```
You racing on torn.com
        │  (TamperMonkey userscript reads the DOM + canvas)
        ▼
  POST http://localhost:8766/data
        │
        ▼
  ws_listener.py ──► session_*.jsonl   (raw frames)
        │        └─► EventDetector ──► events_*.jsonl   (overtakes, lead changes, …)
        │
        ▼
  commentary_worker.py
        ├─ track_mapper.py     → along-track gaps (correct direction)
        ├─ LLM (Sarvam/Claude) → broadcast commentary, ~1 line/min + instant big moments
        ├─ commentary_*.txt    (human-readable, timestamped)
        ├─ commentary_*.jsonl  (structured)
        └─ discord_notify.py   → posts each line to a Discord channel
```

Each stage is a **separate process sharing files**, so a slow LLM call never stalls capture, and any saved race can be replayed through the exact commentary path for testing.

---

## Components

| File | Role |
|---|---|
| `tampermonkey/torn_racing_spy.user.js` | Injected into torn.com. Parses live standings (`#drivers-scrollbar`), track/lap/status, your car's detail, and reads `canvas#raceCanvas` pixels for car-marker positions. POSTs `race_state` frames to the listener. |
| `ws_listener.py` | HTTP server (port 8766). Persists raw frames, runs `EventDetector`, prints a live leaderboard, writes detected events. |
| `event_detector.py` | Stateful detector → prioritized events: `race_start`, `overtake`, `lead_change`, `battle`, `closing`, `final_lap`, `race_finished`. Priority 1–5 with per-event cooldowns. |
| `track_mapper.py` | Builds the track centerline from car telemetry (not image tracing) and computes **along-track** gaps via arc-length `s`, not euclidean distance. |
| `commentary_worker.py` | Consumes events (live tail or `--replay`), generates commentary via the LLM, writes `.txt` + `.jsonl`, and posts to Discord. Steady cadence (`--interval`) plus instant P5 moments. |
| `discord_notify.py` | Posts commentary to Discord via webhook **or** bot token (REST API, no async). Reusable standalone or embedded in the worker. |
| `probe.py` | One-off Torn API explorer (v2 racing endpoints). |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # fill in keys (see below)
```

**Install the userscript:** TamperMonkey → new script → paste `tampermonkey/torn_racing_spy.user.js` → save → hard-reload the Torn racing page (`Ctrl+Shift+R`). A `⬤ RacingSpy` pill appears bottom-right.

**Run it (two terminals):**

```bash
# Terminal 1 — capture + event detection
python ws_listener.py

# Terminal 2 — commentary (+ Discord if configured)
python commentary_worker.py --min-priority 3 --interval 60
```

Join a race. Commentary appears in the terminal, in `spy_results/commentary_<stamp>.txt`, and (if configured) in your Discord channel.

**Watch the commentary file live** (it updates externally, so editors may not auto-refresh):
```powershell
Get-Content spy_results\commentary_<stamp>.txt -Wait -Tail 20
```

**Test on a saved race (no live race needed):**
```bash
python commentary_worker.py --replay spy_results/session_<stamp>.jsonl --speed 5
```

---

## Configuration (`.env`)

| Key | Purpose |
|---|---|
| `TORN_API_KEY` | Torn v2 API (track/car metadata, race list) |
| `SARVAM_API_KEY` | Commentary LLM (auto-selected first). Good quality, but a reasoning model — ~20–90 s/line, best for steady cadence, not tick-by-tick. |
| `ANTHROPIC_API_KEY` | Commentary LLM fallback. Claude Haiku ≈ 1–2 s/line — use for true real-time. |
| `DISCORD_WEBHOOK_URL` | Simplest Discord output: a channel webhook (no bot needed). |
| `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` | Post as a bot via the Discord REST API. |

With no LLM key the worker runs in `--dry-run` (prints prompts). With no Discord creds it just skips posting.

---

## Discord

Two ways to send commentary to a server:

- **Webhook (recommended, simplest):** Channel → Settings → Integrations → Webhooks → New Webhook → copy URL into `DISCORD_WEBHOOK_URL`. No bot invite needed.
- **Bot:** invite a bot with *Send Messages*, put its token in `DISCORD_BOT_TOKEN` and the target channel id (Developer Mode → right-click channel → Copy ID) in `DISCORD_CHANNEL_ID`.

Disable posting with `--no-discord`. You can also post a finished race's commentary standalone:
```bash
python discord_notify.py --jsonl spy_results/commentary_<stamp>.jsonl --from-start
```

---

## Tests

```bash
python -m pytest tests/ -q
```
Covers the event detector, track mapper, and Discord routing (network stubbed).

---

## Notes & decisions

- **Track maps come from telemetry, not image tracing** — accumulating the player's marker over one lap traces the road perfectly; ordering by `completion` turns the point cloud into a parameterized centerline.
- **Distance between cars is arc-length along the track**, never straight-line — two cars across a hairpin are close in pixels but far on track.
- **We don't draw our own markers on the canvas** — the game already renders moving cars; the overlay was removed in favour of reading the game's markers + the side leaderboard.
- Run **one** listener at a time (port 8766). A stale listener squatting the port is the usual cause of "no data in terminal".
