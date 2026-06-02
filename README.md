# Live Commentary Agent

An AI-powered live commentary system for Torn City Racing events, delivering real-time, contextual race commentary via Discord (and optionally via TamperMonkey in-browser overlay).

---

## Architecture Overview

```
Torn Racing API
      │
      ▼
  API Poller  ──►  Kafka Topic (race-telemetry)
                        │
                        ▼
               Stream Processor
               (race state diff)
                        │
                        ▼
              AI Commentary Engine
              (Claude, prompt-chain)
                        │
               ┌────────┴────────┐
               ▼                 ▼
         Discord Bot       TamperMonkey
          (channel)        (in-browser)
```

---

## Phases

### Phase 1 — Foundation & API Integration

**Goal:** Understand the Torn Racing data model and establish reliable polling.

- Set up project structure: Python (or Node.js) with config management
- Integrate the [Torn API](https://www.torn.com/swagger.php#/) racing endpoints:
  - Active races (list ongoing races)
  - Race details (positions, lap times, participant stats)
- Implement a polling loop (configurable interval, e.g. every 3–5 seconds)
- Log raw API responses to file for offline analysis of data structure
- Define typed data models for: `Race`, `Participant`, `LapEvent`, `PositionChange`
- Store API key in `.env` (never committed); document setup in this README

**Deliverable:** A script that polls the Torn Racing API and pretty-prints live race state to the console.

---

### Phase 2 — Kafka Streaming Pipeline

**Goal:** Decouple data ingestion from processing via a high-throughput message bus.

- Spin up Kafka locally via Docker Compose (single-broker dev setup)
- Implement a **Kafka Producer** that:
  - Publishes each API poll response as a message to a `race-telemetry` topic
  - Keys messages by `race_id` to ensure ordered processing per race
- Implement a **Kafka Consumer / Stream Processor** that:
  - Consumes raw telemetry messages
  - Computes state diffs (position changes, new lap completions, race start/finish)
  - Publishes structured `RaceEvent` objects to a `race-events` topic
- Define event types: `RaceStarted`, `PositionChanged`, `LapCompleted`, `RaceFinished`, `CrashDetected`

**Deliverable:** A running pipeline where race events flow from API → Kafka → event stream with sub-second processing latency.

---

### Phase 3 — AI Commentary Engine

**Goal:** Generate real-time, contextual commentary from the race event stream.

- Consume the `race-events` Kafka topic
- Maintain a rolling **race narrative context** (last N events, current standings, participant history)
- Design a **prompt-chain strategy**:
  - System prompt: commentary persona (energetic race announcer, Torn City lore)
  - Context block: current race state, standings, notable participants
  - Event prompt: the specific moment to commentate on
- Integrate Claude API with streaming output for low-latency first-token delivery
- Implement **moment detection** to prioritize high-value events:
  - Lead changes
  - Final lap overtakes
  - Photo-finish scenarios
  - Race completion
- Rate-limit AI calls to avoid redundant commentary on minor micro-events
- Cache participant profiles (race history, win rate) to enrich commentary context

**Deliverable:** A commentary engine that takes a `RaceEvent` and returns a 1–3 sentence live commentary string within ~1 second.

---

### Phase 4 — Discord Delivery

**Goal:** Publish live commentary to a Discord channel in real time.

- Create a Discord bot with `discord.py` (or `discord.js`)
- Configure a dedicated race commentary channel (or thread per race)
- On `RaceStarted`: post a race preview embed (participants, track, odds)
- On commentary output: post messages with:
  - Commentary text
  - Current leaderboard (compact, updated in-place via message edit)
  - Lap/position badge
- Implement deduplication to avoid posting the same moment twice
- Add a `!race` command to show current standings on demand
- Handle race concurrency (multiple races running simultaneously → separate threads)

**Deliverable:** A Discord bot that posts live, AI-generated commentary throughout a race from start to finish.

---

### Phase 5 — TamperMonkey In-Browser Alternative *(Optional)*

**Goal:** Deliver commentary as an overlay on the Torn racing page itself, without requiring Discord.

- Write a TamperMonkey userscript that runs on `https://www.torn.com/page.php?sid=racing`
- Extract race state directly from the page DOM (positions, timers, participant names)
- Send extracted state to a local commentary backend via `fetch` or WebSocket
- Receive commentary text back and inject it into the page as a styled overlay panel
- This approach bypasses API rate limits and captures data the public API may not expose

**Deliverable:** A `.user.js` script + local server that renders AI commentary inline on the Torn racing page.

---

### Phase 6 — Optimization & Hardening

**Goal:** Make the system production-grade for sustained use.

- Latency profiling: measure API poll → Kafka → AI → Discord end-to-end
- Prompt optimization: tune context window size vs. latency tradeoff
- Kafka tuning: partition count, consumer group offsets, retention policy
- Reconnection logic: handle Torn API downtime, Discord rate limits, Kafka broker restarts
- Observability: structured logging, basic metrics (events/sec, AI latency p50/p99)
- Multi-race support: stress test with N concurrent races
- Deployment: containerize all components with Docker Compose for one-command startup

**Deliverable:** A stable, containerized system that can run 24/7 with no manual intervention.

---

## Setup

```bash
# 1. Clone and install dependencies
git clone <repo>
cd live-commentary-agent
pip install -r requirements.txt   # or npm install

# 2. Configure environment
cp .env.example .env
# Add your Torn API key and Discord bot token to .env

# 3. Start Kafka (Phase 2+)
docker compose up -d kafka

# 4. Run the pipeline
python main.py
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data ingestion | Torn REST API, Python `httpx` |
| Message bus | Apache Kafka (Confluent / Docker) |
| Stream processing | Kafka Consumers, Python |
| AI inference | Claude API (streaming, prompt-chaining) |
| Discord delivery | `discord.py` |
| In-browser overlay | TamperMonkey userscript |
| Containerization | Docker Compose |
