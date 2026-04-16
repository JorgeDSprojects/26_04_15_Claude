# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Unified Namespace (UNS) platform for industrial IoT, built around an MQTT broker (EMQX) as the central message bus. The reference use case is a wind farm with 6 turbines (AeroNorth Wind Farm), but the data model is domain-agnostic — any ISA-95 hierarchy works.

The project is also a structured learning platform (10 progressive modules). Module tutorials live in `docs/es/` (Spanish, **never edit**). Technical reference docs live in `docs/en/` (English, authoritative).

## Current state

The repository currently contains only documentation and planning files. No `services/` directories exist yet — they are built progressively module by module. When a service directory does not exist, create it following the structure in `docs/en/01-conventions.md`.

## Development plan and test guides

- **Full roadmap:** [docs/plan/recursive-tickling-oasis.md](docs/plan/recursive-tickling-oasis.md) — 10 modules, each with Goal / Build steps / Hito (hard gate) / Tutorial checkpoint. Read this before starting any module.
- **Module test guides:** `docs/test/module_N_test.md` — one file per module, written by Claude after the module is built. Explains exactly how to verify the module's deliverables end-to-end.
  - [docs/test/module_1_test.md](docs/test/module_1_test.md) — Module 1: broker and first messages

Do not advance to module N+1 until module N's hito passes and Jorge has written `docs/es/1X-modulo-0N-*.md`.

## Read before coding

Always read these in order before touching code:

1. [docs/en/00-architecture.md](docs/en/00-architecture.md) — component map, ports, interaction table
2. [docs/en/01-conventions.md](docs/en/01-conventions.md) — Python structure, naming, SQL, MQTT, REST, WebSocket, frontend conventions
3. [docs/en/02-data-model.md](docs/en/02-data-model.md) — full Postgres schema with design decisions
4. [docs/en/03-mqtt-topics.md](docs/en/03-mqtt-topics.md) — topic hierarchy and payload formats
5. [docs/en/04-criticality-model.md](docs/en/04-criticality-model.md) — the 3-level criticality model and its implementation
6. [docs/en/05-flows.md](docs/en/05-flows.md) — end-to-end data flows F1–F8

When a `docs/en/1X-service-*.md` file exists for the service you're editing, read it first.

## Development commands

All services run via Docker Compose. There is no monorepo build tool.

```bash
# Start the full stack
docker compose up -d

# Start specific services
docker compose up -d mqtt-broker postgres timescaledb redis

# View logs
docker compose logs -f api-service

# Run a Python service's tests (from service directory)
cd services/api-service
python -m pytest tests/ -v

# Run a single test
python -m pytest tests/test_signals.py::test_create_signal -v

# Lint and format Python
ruff check app/
ruff format app/

# Create an Alembic migration (from api-service directory)
alembic revision --autogenerate -m "add <table>"
alembic upgrade head
alembic downgrade -1

# Frontend dev (from services/frontend/)
npm install
npm run dev
npm run build
```

## Architecture

```
Producers                  Hub UNS              Consumers
simulator ──MQTT──▶  EMQX Broker  ──▶ telegraf → TimescaleDB + Redis LKV
sync-service ──────▶ (retained)   ──▶ event-ingestor → Postgres events
                                  ──▶ realtime-service → WebSocket clients
                                  ──▶ meta-ingestor → Postgres meta_drift

api-service (FastAPI) ←──── Postgres (registry) ←────── LISTEN/NOTIFY ── sync-service
frontend (React) ──REST──▶ api-service
frontend (React) ──WS───▶  realtime-service
```

**External ports:** EMQX 1883/18083, api-service 8000, realtime-service 8001, frontend 5173, postgres 5432, timescaledb 5433, redis 6379.

**Docker network:** `uns-network` (single bridge). Use service names as hostnames internally.

## Hard rules — do not violate

1. **Postgres is the source of truth.** MQTT retained `$meta` messages are a mirror only.
2. **Frontend never talks MQTT or SQL directly.** Only `api-service` (REST) and `realtime-service` (WebSocket).
3. **Only `sync-service` publishes retained messages.** No other service sets `retain=true`.
4. **Branch on `signal.criticality`, not signal name.** Three levels: `standard`, `buffered`, `critical`.
5. **All Python services are fully async (asyncio).** No blocking I/O. Use `asyncpg`, `aiomqtt`, `redis.asyncio`, `httpx`.
6. **Every schema change needs an Alembic migration AND an update to `docs/en/02-data-model.md` in the same commit.**
7. **No direct DB access from services that don't own the data.** `realtime-service` never queries Postgres; it calls `api-service` via HTTP.
8. **Never edit `docs/es/`.** Human-authored tutorials, may intentionally diverge from code.
9. **Do not add a fourth criticality level.** Discuss with the project owner first.

## Key design details

### Criticality model

| Level      | MQTT QoS | WS Buffer         | Reconnect           |
|------------|----------|-------------------|---------------------|
| `standard` | 0        | in-memory queue   | LKV only, gaps lost |
| `buffered` | 0        | Redis Stream ≤1000| LKV + catch-up      |
| `critical` | 1        | Redis Stream ≤10000| LKV + catch-up     |

`event-ingestor` uses a persistent MQTT session for `critical` signals so the broker queues messages while it's down.

### LISTEN/NOTIFY flow

`sync-service` listens on channel `signals_changed`. On INSERT/UPDATE, it fetches the signal and publishes a retained `$meta` message. On DELETE, it clears the retained message. `realtime-service` subscribes to `$meta/#` and updates its in-memory signal cache — this is how criticality changes propagate at runtime without restarts.

### Redis key patterns

| Key pattern              | Type         | Written by       | Read by           |
|--------------------------|--------------|------------------|-------------------|
| `lkv:<topic>`            | String (JSON)| Telegraf         | realtime-service  |
| `stream:<topic>`         | Stream       | realtime-service | realtime-service  |
| `ws:session:<client_id>` | Hash         | realtime-service | realtime-service  |

### WebSocket protocol (realtime-service)

- Subscribe: `{"action": "subscribe", "topics": ["..."]}`
- Unsubscribe: `{"action": "unsubscribe", "topics": ["..."]}`
- Data from server: `{"topic": "...", "payload": {...}, "ts": <epoch_ms>}`
- Heartbeat: server sends `{"ping": true}` every 30s; client responds `{"pong": true}`

### Signal `topic` field

Precomputed at insert time: `<asset.path>/<namespace_segment>/<signal.name>`.
Namespace segment: `measure` (informative), `events` (operational), `$meta` (descriptive), `$analytics` (analytic).

### Two Postgres instances

- Port **5432** — registry DB: assets, signals, events, users, dashboards, meta_drift. Owned by `api-service`.
- Port **5433** — TimescaleDB: `metrics` hypertable. Written by Telegraf, read by `api-service`.

`metrics` uses `topic TEXT` (no FK) so Telegraf writes without knowing the registry.

## Python service structure

```
services/<service-name>/
├── app/
│   ├── main.py         # lifespan, app factory
│   ├── config.py       # pydantic-settings BaseSettings
│   ├── models/         # SQLAlchemy models (if service owns DB)
│   ├── schemas/        # Pydantic v2 request/response
│   ├── routers/        # FastAPI routers (if HTTP)
│   ├── services/       # Business logic, no framework coupling
│   └── dependencies.py
├── tests/
├── Dockerfile          # python:3.12-slim base
├── pyproject.toml      # dependencies with pinned major versions
└── README.md
```

Config env var prefixes: `API_`, `SYNC_`, `RT_`, `SIM_`. Shared vars (DB, broker) have no prefix.

## Frontend structure

```
services/frontend/src/
├── api/        # HTTP client functions
├── components/ # Shared UI
├── hooks/      # Custom hooks (use-prefix)
├── pages/      # Route-level components
├── widgets/    # GridStack widget components
├── stores/     # Zustand stores
└── utils/      # Pure utilities
```

## Naming conventions

| Thing              | Convention                | Example                           |
|--------------------|---------------------------|-----------------------------------|
| Python modules     | snake_case                | `signal_router.py`                |
| Python classes     | PascalCase                | `SignalCreate`, `SignalResponse`   |
| SQL tables         | snake_case, plural        | `signals`, `asset_types`          |
| SQL columns        | snake_case                | `polling_interval_ms`             |
| MQTT topics        | snake_case, `/`-separated | `aeronorth/windfarm_north/...`    |
| REST endpoints     | `/api/v1/` prefix, plural | `/api/v1/signals`, `/api/v1/assets/{id}` |
| React components   | PascalCase                | `DashboardEditor.jsx`             |
| React hooks        | camelCase, use-prefix     | `useSignalData.js`                |
| Env vars           | UPPER_SNAKE_CASE          | `POSTGRES_HOST`                   |
| Docker services    | kebab-case                | `api-service`                     |

## Tech stack

| Component     | Technology                          | Version    |
|---------------|-------------------------------------|------------|
| Language      | Python                              | 3.12       |
| API framework | FastAPI                             | ≥ 0.115    |
| ORM           | SQLAlchemy 2.x async                |            |
| DB driver     | asyncpg                             |            |
| Migrations    | Alembic (async)                     |            |
| Validation    | Pydantic v2                         |            |
| Auth          | fastapi-users (JWT)                 |            |
| Admin panel   | SQLAdmin                            |            |
| MQTT client   | aiomqtt                             |            |
| Redis client  | redis-py (asyncio)                  |            |
| HTTP client   | httpx                               |            |
| Linter/fmt    | ruff                                |            |
| Logging       | structlog                           |            |
| Broker        | EMQX                                | 5.x        |
| Registry DB   | PostgreSQL                          | 16         |
| Time-series   | TimescaleDB                         | (PG16 ext) |
| Cache/buffer  | Redis                               | 7.x        |
| Ingestion     | Telegraf                            | ≥ 1.30     |
| Frontend      | React 18 + Vite                     |            |
| Layout        | GridStack                           | 10.x       |
| Charts        | Plotly.js                           |            |
| Node runtime  | Node.js                             | 20         |

## Common tasks — where to start

| Task                         | Start here                                                             |
|------------------------------|------------------------------------------------------------------------|
| Add a new signal type        | `docs/en/02-data-model.md` → `services/api-service/app/models/`       |
| Add a new MQTT topic pattern | `docs/en/03-mqtt-topics.md` → update producers and consumers           |
| Add a new REST endpoint      | `docs/en/01-conventions.md` (REST section) → `services/api-service/app/routers/` |
| Add a new dashboard widget   | `services/frontend/src/widgets/`                                       |
| Modify Postgres schema       | Alembic migration + update `docs/en/02-data-model.md`                 |
| Add a new event type         | `docs/en/02-data-model.md` (events table) → `services/event-ingestor/`|
| Debug MQTT message flow      | `docs/en/05-flows.md` → `docker compose logs -f <service>`            |
| Add a new criticality level  | **DO NOT.** Discuss with the project owner first.                      |
