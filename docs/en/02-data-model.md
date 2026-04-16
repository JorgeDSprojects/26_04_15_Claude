# 02 — Data Model

## Overview

Two separate Postgres instances:

1. **Registry DB** (`postgres` service, port 5432): assets, signals,
   events, users, dashboards, drift. Owned by `api-service`.
2. **TimescaleDB** (`timescaledb` service, port 5433): hypertable
   `metrics` for time-series telemetry. Written by `telegraf`, read by
   `api-service`.

This document covers the Registry DB schema. For the TimescaleDB
hypertable, see the Telegraf section below.

## Entity relationship diagram (text)

```
asset_types 1──────N assets
                    │
                    │ parent_id (self-referencing tree)
                    │
                    ├──N signals ──── signal_types
                    │
                    ├──N events
                    │
                    └── (dashboards reference signals via widgets.config JSONB)

users ──── dashboards 1──N widgets

meta_drift (standalone, no FK to signals — holds unregistered topics)
```

## Enums

```sql
CREATE TYPE criticality_level AS ENUM ('standard', 'buffered', 'critical');
CREATE TYPE signal_datatype AS ENUM ('float', 'int', 'bool', 'string', 'enum');
```

## Tables

### asset_types

Defines the ISA-95 level categories. Seeded at init, rarely changes.

```sql
CREATE TABLE asset_types (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,      -- "enterprise", "wind_turbine", "nacelle"
    isa95_level     TEXT NOT NULL CHECK (isa95_level IN
                    ('enterprise', 'site', 'area', 'line', 'cell')),
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Seed data for wind farm:**

| name            | isa95_level |
|-----------------|-------------|
| enterprise      | enterprise  |
| wind_farm       | site        |
| sector          | area        |
| wind_turbine    | line        |
| rotor           | cell        |
| nacelle         | cell        |
| generator       | cell        |
| gearbox         | cell        |
| tower           | cell        |
| controller      | cell        |

### assets

Hierarchical tree of physical or logical assets. Self-referencing via
`parent_id`. The `path` column stores the full MQTT topic prefix for
this asset, computed from the hierarchy.

```sql
CREATE TABLE assets (
    id              SERIAL PRIMARY KEY,
    parent_id       INTEGER REFERENCES assets(id) ON DELETE RESTRICT,
    asset_type_id   INTEGER NOT NULL REFERENCES asset_types(id),
    code            TEXT NOT NULL,            -- "turbine_03"
    display_name    TEXT NOT NULL,            -- "Turbine 03"
    path            TEXT NOT NULL UNIQUE,     -- "aeronorth/windfarm_north/sector_a/turbine_03"
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (parent_id, code)
);

CREATE INDEX idx_assets_path ON assets (path);
CREATE INDEX idx_assets_parent ON assets (parent_id);
```

**Design decisions:**

- `ON DELETE RESTRICT` on parent: prevents accidentally deleting an
  enterprise and cascading the whole tree. Deletion must be bottom-up.
- `path` is denormalized and precomputed. It must be recalculated when
  an asset moves in the hierarchy. A trigger or application-level logic
  handles this.
- `UNIQUE (parent_id, code)` prevents two siblings with the same code.
  Root asset has `parent_id = NULL`, and the UNIQUE constraint in
  Postgres treats NULLs as distinct, so multiple root assets are allowed
  (one per enterprise). If single-enterprise is enforced, add a partial
  unique index: `CREATE UNIQUE INDEX ON assets (code) WHERE parent_id IS NULL;`
- `metadata` JSONB: extensible key-value for domain-specific attributes
  (manufacturer, model, lat/lon, commissioning_date, etc.).

### signal_types

Namespace types per UNS/ISA-95.

```sql
CREATE TABLE signal_types (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,     -- "informative", "operational", "descriptive", "analytic"
    description     TEXT
);
```

**Seed data:**

| name         | description                              |
|--------------|------------------------------------------|
| informative  | Real-time telemetry (measure)            |
| operational  | Events, alarms, state changes            |
| descriptive  | Static metadata ($meta)                  |
| analytic     | Computed KPIs and predictions            |

### signals

The core registry table. Each row represents one signal in the UNS.

```sql
CREATE TABLE signals (
    id                  SERIAL PRIMARY KEY,
    asset_id            INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    signal_type_id      INTEGER NOT NULL REFERENCES signal_types(id),
    name                TEXT NOT NULL,            -- "rpm", "active_power"
    display_name        TEXT NOT NULL,            -- "Rotor RPM"
    unit                TEXT,                     -- "rpm", "kW", null for enums/bools
    datatype            signal_datatype NOT NULL,
    criticality         criticality_level NOT NULL DEFAULT 'standard',
    topic               TEXT NOT NULL UNIQUE,     -- full MQTT topic, computed
    enabled             BOOLEAN NOT NULL DEFAULT true,

    -- Level B-ready fields (informative in Level A, executable in Level B)
    protocol            TEXT,                     -- "modbus", "opcua", "simulated", "manual"
    connection_config   JSONB DEFAULT '{}'::jsonb,
    polling_interval_ms INTEGER,

    -- Validation hints
    min_value           DOUBLE PRECISION,
    max_value           DOUBLE PRECISION,
    enum_values         JSONB,                    -- for datatype='enum': {"0":"STOP","1":"RUN",...}

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, name)
);

CREATE INDEX idx_signals_asset ON signals (asset_id);
CREATE INDEX idx_signals_criticality ON signals (criticality);
CREATE INDEX idx_signals_enabled ON signals (enabled) WHERE enabled = true;
CREATE INDEX idx_signals_topic ON signals (topic);
```

**Design decisions:**

- `topic` is UNIQUE and precomputed. Format:
  `<asset.path>/<namespace_segment>/<signal.name>`.
  Namespace segment depends on signal_type: `measure` for informative,
  `events` for operational, `$meta` for descriptive, `$analytics` for
  analytic.
- `ON DELETE CASCADE` from assets: if an asset is removed (after all its
  children are removed), its signals go too. This is correct because a
  signal without an asset is meaningless.
- `connection_config` JSONB: protocol-specific configuration. Examples:
  - Modbus: `{"ip": "10.0.1.50", "port": 502, "register": 40001, "type": "holding"}`
  - OPC-UA: `{"endpoint": "opc.tcp://...", "node_id": "ns=2;s=Temp"}`
  - Simulated: `{"csv_file": "turbine_data.csv", "column": "wind_speed"}`
- `enum_values` is used only when `datatype = 'enum'`. The values are
  stored as a JSON object mapping integer codes to string labels.
- `min_value` / `max_value`: used by the frontend for gauge ranges and
  by future validation logic to flag out-of-range values.

### events

Operational events persisted by `event-ingestor`.

```sql
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,            -- "emergency_stop", "overtemperature"
    severity        TEXT NOT NULL CHECK (severity IN
                    ('info', 'warning', 'error', 'critical')),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by INTEGER REFERENCES users(id),
    CONSTRAINT fk_events_ack_user FOREIGN KEY (acknowledged_by) REFERENCES users(id)
);

CREATE INDEX idx_events_asset ON events (asset_id);
CREATE INDEX idx_events_occurred ON events (occurred_at DESC);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_unack ON events (acknowledged_at) WHERE acknowledged_at IS NULL;
```

**Design decisions:**

- `BIGSERIAL` because events can accumulate fast.
- `occurred_at` is the timestamp from the source (when it happened).
  `received_at` is when the ingestor wrote it (when we learned about it).
  The gap between these two reveals ingestion latency.
- Partial index on `acknowledged_at IS NULL` for fast "show me unacked
  alarms" queries.
- NOT a TimescaleDB hypertable. Events have relational structure
  (acknowledgment, FK to users) and OLTP query patterns.

### meta_drift

Records topics that appear in the broker but are NOT registered in the
`signals` table. Populated by `meta-ingestor`.

```sql
CREATE TABLE meta_drift (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    payload         JSONB NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'reviewed', 'imported', 'ignored'))
);

CREATE INDEX idx_drift_status ON meta_drift (status) WHERE status = 'pending';
```

### dashboards

User-created dashboard layouts.

```sql
CREATE TABLE dashboards (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    owner_id        INTEGER REFERENCES users(id),
    layout          JSONB NOT NULL DEFAULT '[]'::jsonb,  -- GridStack serialized layout
    is_public       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### widgets

Individual widgets inside a dashboard.

```sql
CREATE TABLE widgets (
    id              SERIAL PRIMARY KEY,
    dashboard_id    INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    widget_type     TEXT NOT NULL,            -- "line_chart", "gauge", "alarm_list", "asset_info"
    title           TEXT NOT NULL,
    config          JSONB NOT NULL,           -- {"signal_ids": [1,2,3], "time_range": "1h", ...}
    grid_x          INTEGER NOT NULL,
    grid_y          INTEGER NOT NULL,
    grid_w          INTEGER NOT NULL,
    grid_h          INTEGER NOT NULL
);

CREATE INDEX idx_widgets_dashboard ON widgets (dashboard_id);
```

**`config` JSONB structure by widget type:**

| widget_type    | config keys                                         |
|----------------|-----------------------------------------------------|
| `line_chart`   | `signal_ids`, `time_range`, `y_axis_label`, `color` |
| `gauge`        | `signal_id`, `min`, `max`, `thresholds`              |
| `alarm_list`   | `asset_ids`, `severity_filter`, `max_items`          |
| `asset_info`   | `asset_id`                                           |
| `value_card`   | `signal_id`, `label`, `unit`                         |

### users

Managed by `fastapi-users`. This is the minimum schema; fastapi-users
may add additional columns.

```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_superuser    BOOLEAN NOT NULL DEFAULT false,
    is_verified     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## LISTEN/NOTIFY trigger

The `sync-service` reacts to changes in the `signals` table in real
time via Postgres LISTEN/NOTIFY. A trigger fires on every INSERT,
UPDATE, or DELETE.

```sql
CREATE OR REPLACE FUNCTION notify_signal_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'signals_changed',
        json_build_object(
            'op', TG_OP,
            'id', COALESCE(NEW.id, OLD.id)
        )::text
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER signals_notify
AFTER INSERT OR UPDATE OR DELETE ON signals
FOR EACH ROW EXECUTE FUNCTION notify_signal_change();
```

**Notification payload example:**

```json
{"op": "INSERT", "id": 42}
{"op": "UPDATE", "id": 42}
{"op": "DELETE", "id": 42}
```

The `sync-service` receives this, queries the full signal row (for
INSERT/UPDATE) or removes the retained message (for DELETE).

A similar trigger exists for `assets`:

```sql
CREATE OR REPLACE FUNCTION notify_asset_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'assets_changed',
        json_build_object(
            'op', TG_OP,
            'id', COALESCE(NEW.id, OLD.id)
        )::text
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER assets_notify
AFTER INSERT OR UPDATE OR DELETE ON assets
FOR EACH ROW EXECUTE FUNCTION notify_asset_change();
```

## TimescaleDB hypertable (separate instance)

Written by Telegraf, read by `api-service` for historical queries.

```sql
CREATE TABLE metrics (
    time            TIMESTAMPTZ NOT NULL,
    topic           TEXT NOT NULL,
    value           DOUBLE PRECISION,
    quality         SMALLINT DEFAULT 1
);

SELECT create_hypertable('metrics', 'time');

CREATE INDEX idx_metrics_topic_time ON metrics (topic, time DESC);
```

**Design decisions:**

- `topic` as TEXT rather than FK to signals: Telegraf writes raw, with
  no knowledge of the registry. The api-service joins by topic string
  when needed.
- `value` as DOUBLE PRECISION: covers float and int signals. Bool is
  stored as 0/1. String/enum signals are NOT stored in this table (they
  go to events or a separate table if needed).
- Retention policy: `SELECT add_retention_policy('metrics', INTERVAL '1 year');`
  (configurable).
- Continuous aggregates can be added later for hourly/daily rollups.

## Redis key structure

| Pattern                     | Type         | Purpose                          | Written by         | Read by            |
|-----------------------------|-------------|----------------------------------|--------------------|--------------------|
| `lkv:<topic>`               | String (JSON)| Last known value for a signal    | Telegraf           | realtime-service   |
| `stream:<topic>`            | Stream       | Continuity buffer (buffered/critical signals) | realtime-service | realtime-service |
| `ws:session:<client_id>`    | Hash         | Last stream ID per topic per WS client | realtime-service | realtime-service |

**LKV value format:**
```json
{"val": 12.5, "ts": 1705400100500, "q": 1}
```

**Stream entry format:**
Same as LKV but stored as stream fields, not JSON string.
