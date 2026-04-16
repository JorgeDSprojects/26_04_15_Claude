-- =============================================================
-- AeroNorth UNS — Registry schema
-- =============================================================

-- ---------- Asset hierarchy (ISA-95) ----------

CREATE TABLE asset_types (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    isa95_level     TEXT NOT NULL CHECK (isa95_level IN
                    ('enterprise', 'site', 'area', 'line', 'cell')),
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

-- ---------- Signal definitions ----------

CREATE TABLE signal_types (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,     -- "informative", "operational", etc.
    description     TEXT
);

CREATE TYPE criticality_level AS ENUM ('standard', 'buffered', 'critical');
CREATE TYPE signal_datatype AS ENUM ('float', 'int', 'bool', 'string', 'enum');

CREATE TABLE signals (
    id                  SERIAL PRIMARY KEY,
    asset_id            INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    signal_type_id      INTEGER NOT NULL REFERENCES signal_types(id),
    name                TEXT NOT NULL,        -- "rpm", "active_power"
    display_name        TEXT NOT NULL,        -- "Generator RPM"
    unit                TEXT,                 -- "rpm", "kW", null for enums
    datatype            signal_datatype NOT NULL,
    criticality         criticality_level NOT NULL DEFAULT 'standard',
    topic               TEXT NOT NULL UNIQUE, -- computed from asset path + name
    enabled             BOOLEAN NOT NULL DEFAULT true,

    -- Level B-ready (informative in level A, executable later)
    protocol            TEXT,                 -- "modbus", "opcua", "simulated", "manual"
    connection_config   JSONB DEFAULT '{}'::jsonb,
    polling_interval_ms INTEGER,

    -- Validation hints
    min_value           DOUBLE PRECISION,
    max_value           DOUBLE PRECISION,
    enum_values         JSONB,                -- for datatype='enum'

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, name)
);

CREATE INDEX idx_signals_asset ON signals (asset_id);
CREATE INDEX idx_signals_criticality ON signals (criticality);
CREATE INDEX idx_signals_enabled ON signals (enabled);

-- ---------- Events (operational, persisted) ----------

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
    acknowledged_by INTEGER                   -- FK to users, added later
);

CREATE INDEX idx_events_asset ON events (asset_id);
CREATE INDEX idx_events_occurred ON events (occurred_at DESC);
CREATE INDEX idx_events_unack ON events (acknowledged_at) WHERE acknowledged_at IS NULL;

-- ---------- Drift detection ----------

CREATE TABLE meta_drift (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    payload         JSONB NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'reviewed', 'imported', 'ignored'))
);

-- ---------- Dashboards ----------

CREATE TABLE dashboards (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    owner_id        INTEGER,                  -- FK to users
    layout          JSONB NOT NULL DEFAULT '[]'::jsonb,  -- GridStack layout
    is_public       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE widgets (
    id              SERIAL PRIMARY KEY,
    dashboard_id    INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    widget_type     TEXT NOT NULL,            -- "chart", "gauge", "table", "alarm"
    title           TEXT NOT NULL,
    config          JSONB NOT NULL,           -- signal_ids, chart options, etc.
    grid_x          INTEGER NOT NULL,
    grid_y          INTEGER NOT NULL,
    grid_w          INTEGER NOT NULL,
    grid_h          INTEGER NOT NULL
);

-- ---------- Users (managed by fastapi-users) ----------

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_superuser    BOOLEAN NOT NULL DEFAULT false,
    is_verified     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- LISTEN/NOTIFY trigger for sync-service ----------

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