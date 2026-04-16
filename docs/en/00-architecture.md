# 00 — Architecture Overview

## System purpose

AeroNorth UNS is an industrial data platform that implements the Unified
Namespace pattern. An MQTT broker acts as the central message bus. All
producers publish to the broker; all consumers subscribe. No component
knows about any other component — they only know the broker and the
topic hierarchy.

## Components

### Producers (publish to MQTT)

| Service          | Language | Publishes to                     | Notes                                       |
|------------------|----------|----------------------------------|---------------------------------------------|
| `simulator`      | Python   | `measure/#`, `events/#`          | Reads Kaggle CSV + synthetic events          |
| `sync-service`   | Python   | `$meta/#` (retained)             | Mirrors Postgres registry → MQTT             |

### Hub

| Service          | Technology | Ports                            | Notes                                       |
|------------------|------------|----------------------------------|---------------------------------------------|
| `mqtt-broker`    | EMQX 5.x  | 1883 (internal), 8883 (TLS future), 18083 (dashboard) | Persistence enabled, ACLs per topic |

### Consumers (subscribe from MQTT)

| Service              | Language | Subscribes to          | Writes to                  | Notes                                |
|----------------------|----------|------------------------|----------------------------|--------------------------------------|
| `telegraf`           | Config   | `+/+/+/+/+/measure/#` | TimescaleDB + Redis (LKV)  | No custom code, config-only          |
| `event-ingestor`     | Python   | `+/+/+/+/+/events/#`  | Postgres `events` table    | QoS 1, persistent session            |
| `meta-ingestor`      | Python   | `+/+/+/+/+/$meta/#`   | Postgres `meta_drift` table| Drift detection only                 |
| `realtime-service`   | Python   | Varies by criticality  | WebSocket to browsers      | In-memory queue / Redis Streams      |

### Data stores

| Service          | Technology       | Purpose                          | Owned by                  |
|------------------|------------------|----------------------------------|---------------------------|
| `postgres`       | PostgreSQL 16    | UNS registry, events, users, dashboards | `api-service` (write), others (read via API) |
| `timescaledb`    | TimescaleDB      | Historical telemetry (hypertable)| `telegraf` (write), `api-service` (read)     |
| `redis`          | Redis 7.x        | LKV cache + WS continuity buffer| `telegraf` (LKV write), `realtime-service` (Streams + LKV read) |

### API and frontend

| Service          | Technology                          | Purpose                                      |
|------------------|-------------------------------------|----------------------------------------------|
| `api-service`    | FastAPI + SQLAlchemy + SQLAdmin      | REST CRUD, timeseries queries, admin, auth   |
| `frontend`       | React 18 + Vite + GridStack + Plotly | Dynamic dashboards, signal management UI      |

## Component interaction map

```
                        ┌─────────────────────────────┐
                        │       EMQX Broker            │
                        │       (mqtt-broker)           │
                        └──┬──┬──┬──┬──┬───────────────┘
                           │  │  │  │  │
        ┌──────────────────┘  │  │  │  └──────────────────┐
        │              ┌──────┘  │  └──────┐              │
        ▼              ▼         ▼         ▼              ▼
   ┌─────────┐  ┌───────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
   │telegraf  │  │event-     │ │real- │ │meta-     │ │sync-     │
   │          │  │ingestor   │ │time- │ │ingestor  │ │service   │
   │          │  │           │ │svc   │ │          │ │          │
   └──┬───┬──┘  └─────┬─────┘ └──┬───┘ └─────┬────┘ └────┬────┘
      │   │           │          │            │           │
      │   │           │          │            │     LISTEN/NOTIFY
      ▼   ▼           ▼          │            ▼           │
  ┌────┐┌─────┐  ┌────────┐     │       ┌────────┐       │
  │TSdb││Redis│  │Postgres│     │       │Postgres│◄──────┘
  └────┘└──┬──┘  │(events)│     │       │(regist)│
           │     └────────┘     │       └───┬────┘
           │                    │           │
           │              ┌─────┴────┐      │
           │              │WebSocket │      │
           │              │clients   │      │
           │              └──────────┘      │
           │                                │
           │         ┌──────────────┐       │
           └────────▶│  api-service │◄──────┘
                     │  (FastAPI)   │
                     └──────┬──────┘
                            │ REST
                     ┌──────┴──────┐
                     │  frontend   │
                     │  (React)    │
                     └─────────────┘
```

### Arrow legend

| From               | To                  | Protocol         | Direction | Purpose                        |
|--------------------|---------------------|------------------|-----------|--------------------------------|
| simulator          | mqtt-broker         | MQTT pub         | →         | Telemetry + events             |
| sync-service       | mqtt-broker         | MQTT pub retained| →         | $meta descriptive data         |
| mqtt-broker        | telegraf            | MQTT sub         | →         | Informative telemetry          |
| mqtt-broker        | event-ingestor      | MQTT sub QoS 1   | →         | Operational events             |
| mqtt-broker        | realtime-service    | MQTT sub         | →         | All topics (fan-out to WS)     |
| mqtt-broker        | meta-ingestor       | MQTT sub         | →         | $meta topics (drift check)     |
| telegraf           | timescaledb         | SQL INSERT       | →         | Persist metrics                |
| telegraf           | redis               | SET              | →         | Last known value per topic     |
| event-ingestor     | postgres            | SQL INSERT       | →         | Persist events                 |
| meta-ingestor      | postgres            | SQL INSERT       | →         | Drift records                  |
| sync-service       | postgres            | LISTEN           | ←         | React to registry changes      |
| api-service        | postgres            | SQL              | ↔         | CRUD registry, read events     |
| api-service        | timescaledb         | SQL SELECT       | →         | Historical queries             |
| realtime-service   | redis               | XADD/XREAD + GET | ↔        | Buffer + LKV                   |
| frontend           | api-service         | HTTP REST        | ↔         | Config, CRUD, timeseries       |
| frontend           | realtime-service    | WebSocket        | ↔         | Real-time signal values        |

## What does NOT exist (and why)

- **No frontend → MQTT connection.** Security boundary: auth, filtering
  and throttling happen in realtime-service, not in the browser.
- **No frontend → database connection.** All data access via api-service.
- **No LLM service (yet).** The architecture is ready — it will connect
  as another consumer of the REST API and WebSocket, like the frontend.
- **No Sparkplug B.** Plain MQTT with ISA-95 topic hierarchy. See
  project knowledge docs for rationale on Sparkplug limitations.

## Docker Compose service names

```yaml
services:
  mqtt-broker:        # EMQX
  postgres:           # Registry database
  timescaledb:        # Time-series database
  redis:              # Cache and buffer
  telegraf:           # MQTT → TimescaleDB + Redis ingestor
  api-service:        # FastAPI REST API
  sync-service:       # Postgres → MQTT $meta sync
  realtime-service:   # MQTT → WebSocket fan-out
  simulator:          # Wind farm data simulator
  event-ingestor:     # MQTT events → Postgres
  meta-ingestor:      # MQTT $meta drift detection
  frontend:           # React dev server (or nginx in prod)
```

## Network topology

All services connect to a single Docker bridge network (`uns-network`).
Internal service names are used as hostnames. External access:

| Port  | Service          | Purpose                |
|-------|------------------|------------------------|
| 1883  | mqtt-broker      | MQTT (internal only)   |
| 18083 | mqtt-broker      | EMQX dashboard         |
| 8000  | api-service      | REST API               |
| 8001  | realtime-service | WebSocket endpoint     |
| 5173  | frontend         | Vite dev server        |
| 5432  | postgres         | Registry DB (dev only) |
| 5433  | timescaledb      | TimescaleDB (dev only) |
| 6379  | redis            | Redis (dev only)       |
