# 01 — Conventions

## Language policy

- **Code, identifiers, file names, table names, API endpoints, commit
  messages, comments, docstrings**: English.
- **User-facing strings in frontend**: English by default, localization
  layer may be added later.
- **Documentation in `docs/en/`**: English.
- **Documentation in `docs/es/`**: Spanish. Claude Code must NOT edit
  these files.

## Python

### Style

- Python 3.12 minimum. Use modern syntax (type hints, `match`, f-strings).
- Formatter: `ruff format`. Linter: `ruff check`.
- Line length: 88 characters (ruff default).
- Imports: sorted by `ruff` (isort-compatible).
- No `print()` in production code. Use `structlog` for logging.
- All I/O must be async. No blocking calls in request/event paths.

### Naming

| Thing            | Convention     | Example                    |
|------------------|----------------|----------------------------|
| Modules          | snake_case     | `signal_router.py`         |
| Classes          | PascalCase     | `SignalCreate`             |
| Functions        | snake_case     | `get_signal_by_topic()`    |
| Constants        | UPPER_SNAKE    | `MAX_BUFFER_SIZE`          |
| Private          | _leading       | `_build_topic()`           |
| Pydantic models  | PascalCase     | `SignalResponse`           |
| SQLAlchemy models| PascalCase singular | `Signal`, `Asset`    |
| Env vars         | UPPER_SNAKE    | `POSTGRES_HOST`            |

### Project structure per Python service

```
services/<service-name>/
├── app/
│   ├── __init__.py
│   ├── main.py             # Entrypoint, lifespan, app factory
│   ├── config.py           # Settings from env vars (pydantic-settings)
│   ├── models/             # SQLAlchemy models (if service owns DB)
│   ├── schemas/            # Pydantic request/response schemas
│   ├── routers/            # FastAPI routers (if HTTP service)
│   ├── services/           # Business logic, no framework coupling
│   └── dependencies.py     # FastAPI dependency injection
├── tests/
│   ├── conftest.py
│   ├── test_<module>.py
│   └── ...
├── Dockerfile
├── pyproject.toml
└── README.md               # EN, service-specific
```

### Dependencies

- Declare in `pyproject.toml` with `[project.dependencies]`.
- Pin major versions only: `fastapi>=0.115,<1`.
- Dev dependencies in `[project.optional-dependencies] dev`.

### Configuration

- All configuration via environment variables.
- Use `pydantic-settings` `BaseSettings` class in `config.py`.
- Prefix service-specific vars: `API_`, `SYNC_`, `RT_`, `SIM_`.
- Shared vars (DB, broker) have no prefix: `POSTGRES_HOST`, `MQTT_HOST`.
- Never hardcode connection strings, ports, or credentials.

## SQL / PostgreSQL

### Naming

| Thing            | Convention          | Example                   |
|------------------|---------------------|---------------------------|
| Tables           | snake_case, plural  | `signals`, `asset_types`  |
| Columns          | snake_case          | `polling_interval_ms`     |
| Primary keys     | `id`                | `id SERIAL PRIMARY KEY`   |
| Foreign keys     | `<table_singular>_id` | `asset_id`              |
| Indexes          | `idx_<table>_<cols>`| `idx_signals_asset`       |
| Enums (Postgres) | snake_case          | `criticality_level`       |
| Constraints      | Inline or named     | `CHECK (severity IN (...))` |

### Migrations

- Alembic with async driver (asyncpg).
- One migration per logical change.
- Migration message format: `"add <table>" | "alter <table> add <column>"`.
- Always include both `upgrade()` and `downgrade()`.
- Test downgrade locally before committing.

### Timestamps

- All timestamps stored as `TIMESTAMPTZ` (with timezone).
- Application always works in UTC.
- Frontend converts to local time for display.

## MQTT

### Topic naming

- All lowercase, snake_case segments, `/`-separated.
- Follow ISA-95 hierarchy: `enterprise/site/area/line/cell/namespace/signal_name`.
- Namespace segments: `measure` (informative), `$meta` (descriptive),
  `events` (operational), `$analytics` (analytic).
- No trailing slashes.
- No spaces, no special characters except `$` for system topics.

### Payload format

- JSON always. UTF-8 encoded.
- Informative payloads: `{"val": <number>, "ts": <epoch_ms>, "q": <0|1>}`.
- Descriptive payloads ($meta): full JSON object with all signal metadata.
- Event payloads: `{"event_type": "...", "severity": "...", "ts": <epoch_ms>, "data": {...}}`.
- See `docs/en/03-mqtt-topics.md` for complete spec.

## REST API

### URL structure

- Base path: `/api/v1/`.
- Resource-oriented: `/api/v1/signals`, `/api/v1/assets/{id}`.
- Use plural nouns for collections.
- Nested resources max 2 levels: `/api/v1/assets/{id}/signals`.
- Query params for filtering: `/api/v1/signals?criticality=critical&enabled=true`.
- Time-series endpoint: `/api/v1/timeseries?signal_id=...&from=...&to=...`.

### Response format

- Always JSON.
- Collections: `{"items": [...], "total": N, "page": P, "size": S}`.
- Single resource: object directly.
- Errors: `{"detail": "message"}` (FastAPI default).
- HTTP status codes: 200 (ok), 201 (created), 204 (deleted), 400 (bad request), 404 (not found), 422 (validation error).

## WebSocket

### Protocol

- Endpoint: `ws://<realtime-service>/ws`.
- Client sends subscription messages: `{"action": "subscribe", "topics": ["..."]}`.
- Client sends unsubscription: `{"action": "unsubscribe", "topics": ["..."]}`.
- Server sends data messages: `{"topic": "...", "payload": {...}, "ts": <epoch_ms>}`.
- Server sends errors: `{"error": "message"}`.
- Heartbeat: server sends `{"ping": true}` every 30s, client responds `{"pong": true}`.

## Frontend (React)

### Naming

| Thing            | Convention     | Example                    |
|------------------|----------------|----------------------------|
| Components       | PascalCase     | `DashboardEditor.jsx`      |
| Hooks            | camelCase, use-prefix | `useSignalData.js`  |
| Utilities        | camelCase      | `formatTimestamp.js`       |
| Constants        | UPPER_SNAKE    | `WS_RECONNECT_INTERVAL`   |
| CSS classes      | Tailwind utilities | `className="flex gap-2"` |

### Project structure

```
services/frontend/
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── api/                # HTTP client functions
│   ├── components/         # Shared UI components
│   ├── hooks/              # Custom hooks
│   ├── pages/              # Route-level components
│   ├── widgets/            # GridStack widget components
│   ├── stores/             # Zustand stores
│   └── utils/              # Pure utility functions
├── public/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── package.json
└── README.md
```

## Docker

- One `Dockerfile` per service, in the service directory.
- Base images: `python:3.12-slim` for Python, `node:20-slim` for frontend.
- Multi-stage builds for production.
- Development: use `docker-compose.yml` with volume mounts for hot reload.
- Service names in `docker-compose.yml`: kebab-case matching directory names.

## Git

- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`).
- One logical change per commit.
- Branch naming: `feature/<short-description>`, `fix/<short-description>`.
