# Live Commentary Agent

AI-powered live race commentary for Torn City Racing events, delivered via Discord and rendered as an in-browser overlay.

---

## Current Status

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — API Integration | ✅ Done | Torn v2 API working; tracks, cars, race list all mapped |
| Phase 2 — Kafka Pipeline | ⏳ Pending | Deferred; DOM polling via TamperMonkey covers Phase 1–3 needs |
| Phase 3 — AI Commentary | ⏳ Pending | Next after live map is stable |
| Phase 4 — Discord Delivery | ⏳ Pending | — |
| Phase 5 — TamperMonkey Live Map | 🔄 In Progress | Canvas overlay working; canvas marker detection in testing |
| Phase 6 — Optimisation | ⏳ Pending | — |

---

## Architecture (current)

```
Torn racing page DOM
  └── completion % per driver  ──► TamperMonkey script
  └── canvas#raceCanvas pixels ──► marker cluster detection
                                        │
                                        ▼
                               SVG overlay (on game canvas)
                               numbered driver dots + leaderboard pill
                                        │
                                        ▼
                               POST http://localhost:8766/data
                                        │
                                        ▼
                               ws_listener.py  (live leaderboard + overtake detection)
```

---

## How It Works

### TamperMonkey Script (`tampermonkey/torn_racing_spy.user.js`)

Injected into `https://www.torn.com/*`. Does three things every ~1 second (MutationObserver + interval):

1. **DOM parse** — reads `#drivers-scrollbar` for each driver's name and completion %, `div.drivers-list` for track name / lap count / race status, `div.track-wrap` for your own car's position and last lap time.

2. **Canvas marker detection** — calls `canvas#raceCanvas.getContext('2d').getImageData()`, scans for bright saturated pixel clusters (the car marker sprites), returns their centroids. When enough markers are detected (≥ number of drivers), positions are taken directly from pixel coordinates — no path math needed.

3. **SVG overlay** — injects a transparent `<svg>` directly on top of `canvas#raceCanvas`. Numbered coloured circles are placed at either canvas marker coordinates (preferred) or path-interpolated coordinates (fallback). Your car gets a larger circle with a white ring.

Sends `race_state` events to `ws_listener.py` via `GM_xmlhttpRequest POST http://localhost:8766/data`.

### Python Listener (`ws_listener.py`)

Receives `race_state` events, prints a live leaderboard with progress bars and overtake detection, logs canvas marker debug info.

### Track Images & Paths

- 85 track image codes discovered (`A1`–`E17`); letter = car class, number = track layout (17 unique tracks)
- Track images stored in `spy_results/track_images/`
- Fallback SVG paths auto-traced from track images using inner contour algorithm; embedded in script as `TRACK_PATHS` dictionary

---

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Start listener
python ws_listener.py

# Install TamperMonkey in Chrome
# Create new script → paste tampermonkey/torn_racing_spy.user.js → Save
# Hard-reload Torn page (Ctrl+Shift+R)
# Join a race — pill appears bottom-right, dots appear on track canvas
```

---

## API Key

Public Torn API key stored in `.env` (gitignored). See `.env.example`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Live data capture | TamperMonkey userscript, DOM MutationObserver, Canvas `getImageData` |
| Map overlay | SVG injected over game canvas |
| Local relay | Python `http.server` (port 8766) |
| Track paths | scikit-image contour tracing from Torn track images |
| AI commentary (next) | Claude API (streaming) |
| Discord delivery (next) | `discord.py` |
