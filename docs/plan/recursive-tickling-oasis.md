# AeroNorth UNS — Development Plan

## Context

The repository today contains only documentation: `CLAUDE.md`, `README.md`, `orden_didactico.md`, `sql_squema.md`, and the `docs/en/` reference set (00–05). No `services/`, no `docker-compose.yml`, no `.env.example`. Everything must be built from scratch following the 10 progressive modules in [orden_didactico.md](orden_didactico.md).

The project has a dual purpose: it is both a working MVP for an industrial Unified Namespace and a teaching artifact. Each module must end with a *hito visible* — a tangible demonstration the student (and you) can run and see — and each module is followed by a hand-written Spanish tutorial in `docs/es/`. Claude must not write the tutorials, but the plan flags the natural points where you (Jorge) write them.

Architectural ground rules from [CLAUDE.md](CLAUDE.md) and [docs/en/](docs/en/) apply to every module: Postgres is the source of truth, only `sync-service` publishes retained messages, the frontend never talks MQTT or SQL directly, all Python services are async, every schema change carries an Alembic migration plus a `02-data-model.md` update, and the criticality model is fixed at three levels.

## Plan structure

For each module:
- **Goal** — one line.
- **Build steps** — concrete steps Claude executes.
- **Hito (hard gate)** — exact command(s) and observable result that proves the module works. Do not advance until this passes.
- **Tutorial checkpoint** — where Jorge writes the corresponding `docs/es/` file by hand (skipped by Claude).

---

## Module 1 — Broker and first messages

**Goal:** EMQX running, student can pub/sub from the CLI and grasps topics, wildcards, QoS, retained.

**Build steps:**
1. Create `docker-compose.yml` at repo root with a single service `mqtt-broker` (EMQX 5.x, ports 1883 and 18083, named volume for persistence, network `uns-network`).
2. Create `.env.example` with the broker variables (`MQTT_HOST=mqtt-broker`, `MQTT_PORT=1883`, EMQX dashboard credentials).
3. Create a placeholder `services/.gitkeep` so the directory exists.
4. Document the `mosquitto_pub` / `mosquitto_sub` commands the student will run in a top-level `docs/en/cli-cheatsheet.md` (referenced from the tutorial).

**Hito (hard gate):**
```bash
docker compose up -d mqtt-broker
# In terminal A:
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -v
# In terminal B:
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -m '{"val":1}' -r
```
Terminal A must print the message and, after restarting the subscriber, the retained message must arrive again. EMQX dashboard at `http://localhost:18083` must be reachable.

**Tutorial checkpoint:** Jorge writes `docs/es/10-modulo-01-broker.md`.

---

## Module 2 — Simulator and ISA-95 hierarchy

**Goal:** A Python `simulator` service publishes telemetry for **one turbine** with ISA-95 topics. Student sees structured topics arriving live.

**Build steps:**
1. Create `services/simulator/` with the Python service layout from [docs/en/01-conventions.md](docs/en/01-conventions.md): `app/main.py`, `app/config.py`, `app/services/`, `Dockerfile` (`python:3.12-slim`), `pyproject.toml` (deps: `aiomqtt`, `pydantic-settings`, `structlog`).
2. Implement an async loop that, for one turbine (`aeronorth/windfarm_north/sector_a/turbine_03`), publishes to:
   - `.../rotor/measure/rpm`
   - `.../nacelle/measure/wind_speed`
   - `.../generator/measure/active_power`
   Payload format from [docs/en/03-mqtt-topics.md](docs/en/03-mqtt-topics.md): `{"val": <num>, "ts": <epoch_ms>, "q": 1}`. Default 10s interval, configurable via `SIM_INTERVAL_MS`.
3. Values come from a small bundled CSV (no Kaggle dependency yet — synthetic sine waves are fine for Module 2; the real CSV arrives later if needed).
4. Add `simulator` to `docker-compose.yml`. Env vars: `MQTT_HOST`, `MQTT_PORT`, `SIM_INTERVAL_MS`, `SIM_ASSET_PATH`.
5. No retained messages, QoS 0.

**Hito (hard gate):**
```bash
docker compose up -d mqtt-broker simulator
mosquitto_sub -h localhost -p 1883 -t 'aeronorth/windfarm_north/sector_a/turbine_03/+/measure/#' -v
```
Three signals must tick every 10 seconds with valid JSON payloads.

**Tutorial checkpoint:** Jorge writes `docs/es/11-modulo-02-simulator.md`.

---

## Module 3 — Persistence with Telegraf and TimescaleDB

**Goal:** History is queryable. Student understands why a time-series DB exists.

**Build steps:**
1. Add `timescaledb` service (port 5433 external, port 5432 internal) to `docker-compose.yml` with init script that creates the `metrics` hypertable from [docs/en/02-data-model.md](docs/en/02-data-model.md). Init SQL goes in `services/timescaledb/init/01-metrics.sql`.
2. Add `telegraf` service to `docker-compose.yml`. Config in `services/telegraf/telegraf.conf`:
   - `mqtt_consumer` input subscribing to `+/+/+/+/+/measure/#` with `topic_parsing` to extract enterprise/site/area/line/cell/signal tags.
   - `postgresql` output writing to TimescaleDB.
   - Redis output is **deferred to Module 7** — keep telegraf.conf minimal here.
3. Update `.env.example` with TimescaleDB credentials.
4. Update `docs/en/02-data-model.md` only if the schema changes (it shouldn't).

**Hito (hard gate):**
```bash
docker compose up -d
# Wait ~30 seconds for data to accumulate
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "SELECT topic, value, time FROM metrics ORDER BY time DESC LIMIT 10;"
```
Must return rows from the simulator's three signals with monotonically advancing timestamps.

**Tutorial checkpoint:** Jorge writes `docs/es/12-modulo-03-telegraf-timescale.md`.

---

## Module 4 — UNS registry and api-service

**Goal:** Postgres registry exists, FastAPI exposes CRUD for assets and signals, SQLAdmin works.

**Build steps:**
1. Add a separate `postgres` service (port 5432) to `docker-compose.yml` for the registry. Distinct from `timescaledb`.
2. Create `services/api-service/` with the standard layout from [docs/en/01-conventions.md](docs/en/01-conventions.md):
   - `app/main.py` — lifespan, app factory, CORS.
   - `app/config.py` — pydantic-settings (`API_` prefix for service vars).
   - `app/db.py` — async SQLAlchemy engine and session factory using `asyncpg`.
   - `app/models/` — `asset_type.py`, `asset.py`, `signal_type.py`, `signal.py`. Mirror exactly the schema from [docs/en/02-data-model.md](docs/en/02-data-model.md).
   - `app/schemas/` — Pydantic v2 request/response models.
   - `app/routers/` — `assets.py`, `signals.py`, `asset_types.py`, `signal_types.py`.
   - `app/services/topic_builder.py` — `compute_topic()` from [docs/en/03-mqtt-topics.md:167](docs/en/03-mqtt-topics.md#L167). Reuse this everywhere a topic is constructed.
   - `app/admin.py` — SQLAdmin mounted at `/admin`.
3. Set up Alembic with the async template:
   - `alembic/env.py` configured for asyncpg.
   - First migration: `0001_initial.py` containing all enums, asset_types, assets, signal_types, signals (events/users/dashboards/widgets/meta_drift come in later modules — only build what is needed now).
   - Seed data migration: `0002_seed_asset_types_signal_types.py` with the seed rows from [docs/en/02-data-model.md:60](docs/en/02-data-model.md#L60).
4. Endpoints (only what Module 4 needs): `GET/POST/PATCH/DELETE /api/v1/assets`, same for `/api/v1/signals`, plus `GET /api/v1/asset-types` and `GET /api/v1/signal-types`.
5. The `signals` POST handler must compute `topic` server-side via `compute_topic()`. Never accept client-supplied topics.
6. Add `api-service` to `docker-compose.yml`, port 8000, depends on `postgres`. Run `alembic upgrade head` on startup.
7. Update [docs/en/02-data-model.md](docs/en/02-data-model.md) only if reality diverges from the doc (it shouldn't on first creation).

**Hito (hard gate):**
```bash
docker compose up -d postgres api-service
# Visit http://localhost:8000/admin in browser — log in, navigate to Signals
# Create a signal via SQLAdmin: asset turbine_03/rotor, name "rpm", informative, float, criticality "buffered"
# Then:
curl http://localhost:8000/api/v1/signals | jq
```
The created signal must appear with the precomputed topic `aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm`.

**Tutorial checkpoint:** Jorge writes `docs/es/13-modulo-04-api-service.md`.

---

## Module 5 — sync-service and LISTEN/NOTIFY

**Goal:** Postgres is master, MQTT `$meta` is mirror, sync is automatic.

**Build steps:**
1. Add to migration `0003_signal_notify_trigger.py` the `notify_signal_change()` function and trigger from [docs/en/02-data-model.md:315](docs/en/02-data-model.md#L315), and the same for assets (`assets_notify`).
2. Create `services/sync-service/` (Python, async). Structure:
   - `app/main.py` — startup loads all enabled signals from Postgres and republishes their `$meta` retained messages (ensures consistency on cold start).
   - `app/listener.py` — uses `asyncpg` `add_listener()` on channels `signals_changed` and `assets_changed`.
   - `app/publisher.py` — `aiomqtt` client publishing to `<asset.path>/$meta/<signal.name>` with `retain=true`, QoS 1. Payload schema from [docs/en/03-mqtt-topics.md:104](docs/en/03-mqtt-topics.md#L104).
   - On DELETE, publish an empty payload to the same topic to clear the retained message.
3. **Hard rule reminder:** this is the only service allowed to set `retain=true`.
4. Add `sync-service` to `docker-compose.yml`. Env: `POSTGRES_*`, `MQTT_*`, `SYNC_` prefix for its own settings.

**Hito (hard gate):**
```bash
docker compose up -d
# Terminal A:
mosquitto_sub -h localhost -p 1883 -t '+/+/+/+/+/$meta/#' -v
# Terminal B: create a new signal via SQLAdmin or POST /api/v1/signals
```
Within 1 second, terminal A must show the new `$meta` retained message. Restart `mosquitto_sub` — message must arrive again (proves retain). Edit the signal's criticality — terminal A must show the updated payload. Delete the signal — terminal A must show an empty payload (or absence on restart).

**Tutorial checkpoint:** Jorge writes `docs/es/14-modulo-05-sync-service.md`.

---

## Module 6 — Minimal frontend and realtime-service

**Goal:** Live data reaches the browser via WebSocket. No criticality logic yet — everything behaves like `standard`.

**Build steps:**
1. Create `services/realtime-service/` (Python, async):
   - `app/main.py` — FastAPI app with a `/ws` endpoint.
   - `app/mqtt_client.py` — subscribes to `+/+/+/+/+/measure/#` and `+/+/+/+/+/$meta/#`.
   - `app/signal_cache.py` — populated from MQTT `$meta` messages. No direct Postgres access (hard rule).
   - `app/ws_manager.py` — tracks connected clients and per-client subscriptions; in-memory `asyncio.Queue` per client (Module 6 is single-strategy: in-memory only).
   - WebSocket protocol from [docs/en/01-conventions.md:140](docs/en/01-conventions.md#L140): `subscribe`/`unsubscribe` actions, data messages with `topic`/`payload`/`ts`, ping/pong every 30s.
2. Create `services/frontend/` (React 18 + Vite):
   - `src/api/signals.js` — `fetch('/api/v1/signals')`.
   - `src/api/wsClient.js` — wraps the WS protocol, generates a UUID `client_id` stored in `sessionStorage`.
   - `src/widgets/LiveLineChart.jsx` — Plotly.js, subscribes to one signal topic via the WS client, appends points.
   - `src/App.jsx` — fetches signals from the API, renders one `LiveLineChart` for `turbine_03/rotor/measure/rpm`.
   - `vite.config.js` — proxy `/api` → `api-service:8000`, `/ws` → `realtime-service:8001`.
3. Add `realtime-service` (port 8001) and `frontend` (port 5173, Vite dev server) to `docker-compose.yml`.

**Hito (hard gate):**
```bash
docker compose up -d
# Open http://localhost:5173 in a browser
```
A live Plotly line chart must update every 10 seconds with the simulator's RPM value. No browser refresh needed, no manual MQTT or SQL involved.

**Tutorial checkpoint:** Jorge writes `docs/es/15-modulo-06-frontend-realtime.md`.

---

## Module 7 — Criticality, Redis, buffers

**Goal:** The three criticality levels work end-to-end. Killing the browser and reconnecting demonstrates the difference.

**Build steps:**
1. Add `redis` (7.x) service to `docker-compose.yml`, port 6379.
2. Update `services/telegraf/telegraf.conf` to also write LKV to Redis: `SET lkv:<topic> <payload>`. Keys per [docs/en/02-data-model.md:396](docs/en/02-data-model.md#L396).
3. Update `services/realtime-service/`:
   - `app/buffer_strategy.py` — branches on `signal.criticality` (from the in-memory `signal_cache` populated by `$meta`):
     - `standard` → in-memory queue (existing behavior).
     - `buffered` → `XADD stream:<topic>` with `MAXLEN ~ 1000`; client reader uses `XREAD` from last id stored in `ws:session:<client_id>`.
     - `critical` → same but `MAXLEN ~ 10000` (critical also affects MQTT QoS 1 — see Module 8).
   - On WS connect, send the LKV from Redis immediately (`GET lkv:<topic>`) before resuming live (per F4 in [docs/en/05-flows.md:96](docs/en/05-flows.md#L96)).
   - On reconnect from a known `client_id`, `XREAD` the gap from the last seen stream id.
4. Update `services/simulator/` to read criticality per signal from `$meta` (subscribe to the relevant `$meta` topics on startup) so it can pick QoS 0 vs 1 in Module 8.
5. Reuse `compute_topic()` from `api-service` only on the server side; the simulator and realtime-service must never duplicate the function — they consume the topic from `$meta`.
6. Add a second widget to the frontend tied to a `standard` signal so the contrast is visible at the hito.

**Hito (hard gate):**
```bash
docker compose up -d
# In SQLAdmin, set rpm = "buffered" and wind_speed = "standard"
# Open http://localhost:5173, watch both charts tick for 1 minute
# Close the browser tab. Wait 30 seconds. Reopen.
```
The `buffered` chart must show all the points from the 30-second gap (filled in from the Redis Stream). The `standard` chart must show only the latest LKV with no historical fill. Document the exact observation in the hito output.

**Tutorial checkpoint:** Jorge writes `docs/es/16-modulo-07-criticidad-redis.md`.

---

## Module 8 — Events, alarms, and QoS 1

**Goal:** Critical events flow end-to-end with delivery guarantees, even if the ingestor is down.

**Build steps:**
1. Add `events` table to a new Alembic migration `0004_events_users.py` plus the minimum `users` table required by the FK (full `fastapi-users` integration is deferred to a later iteration — for Module 8, a stub `users` table is enough). Schema from [docs/en/02-data-model.md:195](docs/en/02-data-model.md#L195).
2. Create `services/event-ingestor/` (Python, async):
   - `app/main.py` — `aiomqtt` with persistent session (`clean_session=False`, fixed `client_id`), QoS 1 subscription to `+/+/+/+/+/events/#`.
   - `app/handler.py` — resolves `asset_id` from the topic prefix (HTTP call to api-service `GET /api/v1/assets?path=...`), inserts into `events` table.
   - Idempotency: dedup by `(asset_id, event_type, occurred_at)` — see [docs/en/04-criticality-model.md:74](docs/en/04-criticality-model.md#L74).
3. Add a manual injection endpoint to `api-service`: `POST /api/v1/dev/inject-event` that publishes an event message via `aiomqtt` (dev-only, gated by an env flag).
4. Add an `AlarmList` widget to the frontend that subscribes to `+/+/+/+/+/events/#` via the WS protocol (extend `realtime-service` to allow wildcard subscriptions for events).
5. Update the simulator to optionally emit events on threshold breaches (e.g., wind_speed > 25 → `high_wind_cutoff`).
6. Add `event-ingestor` to `docker-compose.yml`.

**Hito (hard gate):**
```bash
docker compose up -d
docker compose stop event-ingestor
# Inject 5 events:
for i in 1 2 3 4 5; do
  curl -X POST http://localhost:8000/api/v1/dev/inject-event \
    -d '{"asset_id": <id>, "event_type": "manual_test", "severity": "warning"}'
done
docker compose start event-ingestor
sleep 5
docker compose exec postgres psql -U postgres -d uns \
  -c "SELECT count(*) FROM events WHERE event_type='manual_test';"
```
Count must equal 5. The frontend AlarmList must also display the 5 alarms once the ingestor catches up. Demonstrates QoS 1 + persistent session.

**Tutorial checkpoint:** Jorge writes `docs/es/17-modulo-08-eventos-alarmas.md`.

---

## Module 9 — Dynamic dashboards with GridStack

**Goal:** Users compose their own dashboards via drag and drop; layouts persist.

**Build steps:**
1. Add `dashboards` and `widgets` tables in migration `0005_dashboards_widgets.py`. Schema from [docs/en/02-data-model.md:247](docs/en/02-data-model.md#L247).
2. Add `api-service` endpoints: `GET/POST/PATCH/DELETE /api/v1/dashboards` and `/api/v1/dashboards/{id}/widgets`.
3. Build the frontend dashboard editor in `services/frontend/src/pages/DashboardEditor.jsx`:
   - GridStack 10.x for the layout grid.
   - Sidebar listing available widget types.
   - Drag a widget type onto the grid → opens a config modal → POSTs to `/api/v1/dashboards/{id}/widgets`.
   - Save layout: serialize GridStack layout → PATCH `/api/v1/dashboards/{id}`.
4. Implement the widgets matching the config table in [docs/en/02-data-model.md:281](docs/en/02-data-model.md#L281): `line_chart`, `gauge`, `alarm_list`, `asset_info`, `value_card`. Place each in `src/widgets/`.
5. Initial-load flow per F5 in [docs/en/05-flows.md:124](docs/en/05-flows.md#L124): widget reads its `signal_id` from config, fetches signal metadata, then subscribes via WS. Historical charts also call `GET /api/v1/timeseries?signal_id=...&from=...&to=...` (add this endpoint to api-service backed by TimescaleDB).
6. Add `pages/DashboardList.jsx` and routing.

**Hito (hard gate):**
- Open `http://localhost:5173/dashboards/new`.
- Drag a `gauge` widget onto the grid, configure it for `wind_speed`, save.
- Drag a `line_chart` widget for `rpm`, save.
- Refresh the page — both widgets reload with their layout intact and start streaming live data.
- All without touching code.

**Tutorial checkpoint:** Jorge writes `docs/es/18-modulo-09-dashboards.md`.

---

## Module 10 — Drift and observability

**Goal:** The system watches itself. Unregistered topics surface for review; basic observability is in place.

**Build steps:**
1. Add `meta_drift` table in migration `0006_meta_drift.py`. Schema from [docs/en/02-data-model.md:230](docs/en/02-data-model.md#L230).
2. Create `services/meta-ingestor/` (Python, async):
   - Subscribes to `+/+/+/+/+/$meta/#`.
   - Maintains an in-memory cache of registered topics fetched from `api-service` (refreshed periodically and on `$meta` updates from `sync-service`).
   - On unknown topic, INSERT into `meta_drift` with status `pending`.
3. Add admin endpoints to `api-service`: `GET /api/v1/drift`, `POST /api/v1/drift/{id}/import` (creates a signal from the drift payload), `POST /api/v1/drift/{id}/ignore`.
4. Build a `DriftReview` page in the frontend listing pending drift items with Import/Ignore buttons.
5. Optional but recommended: add a `/metrics` Prometheus endpoint to each Python service via `prometheus-fastapi-instrumentator` (for `api-service` and `realtime-service`) and a small `prometheus_client` setup for the others. No Prometheus container yet — just expose the endpoints.
6. Demonstrate drift by publishing a `$meta` for a signal that does not exist in the registry (manual `mosquitto_pub` from CLI).

**Hito (hard gate):**
```bash
mosquitto_pub -h localhost -p 1883 -r -t \
  'aeronorth/windfarm_north/sector_a/turbine_03/nacelle/$meta/humidity' \
  -m '{"name":"humidity","unit":"%RH","datatype":"float"}'
# Within seconds:
curl http://localhost:8000/api/v1/drift | jq
```
Must return one pending drift item with `topic` matching the published one. Click "Import" in the frontend → a new signal appears in the registry, a `$meta` retained message is republished by `sync-service`, the drift item flips to `imported`.

**Tutorial checkpoint:** Jorge writes `docs/es/19-modulo-10-drift-observabilidad.md`.

---

## Cross-cutting conventions to enforce in every module

- **Async only.** Every Python I/O call uses `asyncpg`, `aiomqtt`, `redis.asyncio`, or `httpx`. No blocking calls.
- **Migrations + docs in the same commit.** Any schema change updates [docs/en/02-data-model.md](docs/en/02-data-model.md) in the same commit as the Alembic file.
- **Topic computation in one place.** `compute_topic()` lives in `services/api-service/app/services/topic_builder.py`. No reimplementation elsewhere.
- **Retained = sync-service only.** Code review check at every module that touches MQTT publishing.
- **Branch on criticality, not on signal name.** Reviewed at Modules 7, 8, 10.
- **Frontend has zero MQTT/SQL imports.** Only `fetch` to `/api` and the WS client to `/ws`.
- **One `Dockerfile` per service**, multistage in production-style modules (later iteration), simple in early modules.
- **Conventional commits**: `feat(simulator): publish rpm telemetry for one turbine`.

## Verification across modules

After each module's hito passes:
1. Run `docker compose down && docker compose up -d` (cold start) and re-verify the hito. Catches missing init order or volume issues.
2. `docker compose logs <service> | grep -i error` — must be clean.
3. For Modules 4+, run `alembic upgrade head` then `alembic downgrade -1 && alembic upgrade head` to verify reversibility.

## Module 11 (out of scope, future)

Listed in [orden_didactico.md](orden_didactico.md) for context only — the LLM orchestrator. Not part of this plan. The architecture is already prepared: it would consume the same REST + WebSocket endpoints any other client uses.

## What this plan does NOT cover (deliberate exclusions)

- Production hardening (TLS on the broker, secrets management, multi-stage Dockerfile optimization).
- Multi-user auth beyond a stub `users` table — `fastapi-users` JWT integration is deferred until after Module 10.
- Sparkplug B, edge gateways, multi-tenant isolation — explicitly out of scope per [CLAUDE.md](CLAUDE.md).
- Writing anything in `docs/es/` — Jorge writes those tutorials by hand at each tutorial checkpoint above.

## How to use this plan

This is the full roadmap. Execute it module by module. After each module's hito passes and Jorge writes the corresponding `docs/es/` tutorial, return here and start the next module. If reality diverges from the plan during a module, update this file before continuing — do not let the plan and the code drift apart.
