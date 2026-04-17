# Module 3 — Test Guide: Persistence with Telegraf and TimescaleDB

## What this module delivers

- A **TimescaleDB** container (`timescaledb` service, port 5433 external) with a pre-created `metrics` hypertable.
- A **Telegraf** container that subscribes to `+/+/+/+/+/measure/#` on the EMQX broker and writes every incoming measurement to the hypertable.
- The three simulator signals (`rpm`, `wind_speed`, `active_power`) are now permanently stored and queryable via SQL.

---

## Prerequisites

- Module 1 hito passed (EMQX running, pub/sub works).
- Module 2 hito passed (simulator publishes three signals every 10 s).
- Docker and Docker Compose installed.
- A `.env` file at the repo root created from `.env.example`.

---

## Quick start

```bash
# From the repo root
docker compose up -d mqtt-broker simulator timescaledb telegraf
```

Wait ~30 seconds for Telegraf to ingest the first few batches, then run the hito query.

---

## Hito (hard gate)

```bash
docker compose exec timescaledb psql \
  -U postgres -d metrics \
  -c "SELECT topic, value, quality, time FROM metrics ORDER BY time DESC LIMIT 10;"
```

**Expected result:** 10 rows (or fewer if < 30 s elapsed) from the three topics:

```
aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power
```

Each row must have:
- `topic` — the full MQTT topic string.
- `value` — a numeric float.
- `quality` — `1` (good quality).
- `time` — a recent timestamp with monotonically advancing values.

---

## Step-by-step verification

### T1 — TimescaleDB is healthy

```bash
docker compose ps timescaledb
```

Status must be `healthy`. If not:

```bash
docker compose logs timescaledb | tail -30
```

### T2 — Hypertable exists

```bash
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "\d metrics"
```

Expected output:

```
                      Table "public.metrics"
 Column  |            Type             | Nullable |  Default
---------+-----------------------------+----------+-----------
 time    | timestamp with time zone    | not null |
 topic   | text                        | not null |
 value   | double precision            |          |
 quality | smallint                    |          | 1
```

And it must be recognized as a hypertable:

```bash
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"
```

Expected: `metrics`.

### T3 — Telegraf is running and connected

```bash
docker compose ps telegraf
docker compose logs telegraf | grep -i "connected\|error\|warn" | tail -20
```

No ERROR lines. Should see lines like:
```
Connected to broker tcp://mqtt-broker:1883
```

### T4 — Data is accumulating

Run twice, 15 seconds apart:

```bash
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "SELECT COUNT(*) FROM metrics;"
```

The count must increase between runs (each simulator tick adds 3 rows: rpm, wind_speed, active_power).

### T5 — All three signals are present

```bash
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "SELECT topic, COUNT(*), MIN(time), MAX(time) FROM metrics GROUP BY topic ORDER BY topic;"
```

Expected: three rows, one per signal, with `max(time)` within the last 30 seconds.

### T6 — Cold start resilience

```bash
docker compose down
docker compose up -d mqtt-broker simulator timescaledb telegraf
# Wait 40 seconds
docker compose exec timescaledb psql -U postgres -d metrics \
  -c "SELECT topic, value, time FROM metrics ORDER BY time DESC LIMIT 6;"
```

New rows must appear after restart, proving data survives a cold restart (TimescaleDB uses a named volume).

---

## Automated test script

Run the Python script for an automated end-to-end check:

```bash
# Requires: pip install psycopg2-binary (or psycopg[binary])
python scripts/M3_Test/M3_T1.py
```

The script connects to TimescaleDB on `localhost:5433`, waits up to 60 seconds for rows to appear from all three signal topics, and prints PASS/FAIL per check.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `timescaledb` stays `starting` | Extension not loaded | Check `docker compose logs timescaledb` for init errors |
| Telegraf exits with `connection refused` | TimescaleDB not ready | Telegraf has `depends_on: timescaledb: condition: service_healthy`; wait longer |
| No rows in metrics after 60 s | Telegraf can't reach MQTT | Verify `docker compose logs telegraf` — look for MQTT auth errors |
| Rows appear but `topic` is empty | `topic_parsing` misconfigured | Check Telegraf config tags mapping |
| `pgx` driver error in Telegraf logs | Wrong DSN or credentials | Verify `.env` values match `docker-compose.yml` env vars |

---

## Files introduced in Module 3

| File | Purpose |
|---|---|
| [services/timescaledb/init/01-metrics.sql](../../services/timescaledb/init/01-metrics.sql) | Creates the `metrics` hypertable, index, and retention policy |
| [services/telegraf/telegraf.conf](../../services/telegraf/telegraf.conf) | Telegraf pipeline: MQTT → TimescaleDB |
| `.env.example` | Updated with `TIMESCALE_*` variables |
| `docker-compose.yml` | Added `timescaledb` and `telegraf` services |

---

## What comes next

Module 4 introduces the **UNS registry** (Postgres `api-service`) and the FastAPI REST API. TimescaleDB remains write-only from Telegraf; the api-service will later add a `GET /api/v1/timeseries` endpoint for historical queries.
