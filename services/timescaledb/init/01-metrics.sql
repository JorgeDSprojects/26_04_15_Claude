-- TimescaleDB init: metrics hypertable for UNS telemetry
-- Written by telegraf; read by api-service for historical queries.
-- No FK to signals — telegraf writes raw without registry knowledge.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS metrics (
    time    TIMESTAMPTZ NOT NULL,
    topic   TEXT        NOT NULL,
    value   DOUBLE PRECISION,
    quality SMALLINT DEFAULT 1
);

SELECT create_hypertable('metrics', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_metrics_topic_time ON metrics (topic, time DESC);

-- Retain 1 year of data (adjustable)
SELECT add_retention_policy('metrics', INTERVAL '1 year', if_not_exists => TRUE);
