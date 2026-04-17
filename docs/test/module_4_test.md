# Module 4 Test Guide — UNS Registry and api-service

## What was built

- **`postgres`** service: PostgreSQL 16 registry database (port 5432).
- **`api-service`** (FastAPI): REST CRUD for assets, signals, asset types and signal types, plus SQLAdmin UI at `/admin`.
- **Alembic** migrations run on startup: `0001_initial` (schema + enums) + `0002_seed` (asset_type and signal_type rows).
- **`compute_topic()`** in `services/api-service/app/services/topic_builder.py` — the single authoritative implementation.

## Prerequisites

- Modules 1–3 hito passed (broker + simulator + Telegraf/TimescaleDB running).
- Docker and Docker Compose installed.
- `curl` and `jq` available on the host.

## Step 0 — Build and start

```bash
docker compose up -d --build postgres api-service
docker compose logs -f api-service
```

Wait until you see:

```
Running Alembic migrations...
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, seed asset_types and signal_types
Starting API service...
INFO:     Application startup complete.
```

## Step 1 — Health check

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Step 2 — Verify seed data

```bash
curl http://localhost:8000/api/v1/asset-types | jq
# Must return 10 entries: enterprise, wind_farm, sector, wind_turbine, rotor, nacelle, generator, gearbox, tower, controller

curl http://localhost:8000/api/v1/signal-types | jq
# Must return 4 entries: informative, operational, descriptive, analytic
```

## Step 3 — Create the asset hierarchy via REST

Create the full ISA-95 path for turbine_03 bottom-up (parents before children):

```bash
# Enterprise
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"asset_type_id":1,"code":"aeronorth","display_name":"AeroNorth","path":"aeronorth"}' | jq

# Site
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":1,"asset_type_id":2,"code":"windfarm_north","display_name":"Wind Farm North","path":"aeronorth/windfarm_north"}' | jq

# Area
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":2,"asset_type_id":3,"code":"sector_a","display_name":"Sector A","path":"aeronorth/windfarm_north/sector_a"}' | jq

# Line (turbine)
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":3,"asset_type_id":4,"code":"turbine_03","display_name":"Turbine 03","path":"aeronorth/windfarm_north/sector_a/turbine_03"}' | jq

# Cell (rotor)
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":4,"asset_type_id":5,"code":"rotor","display_name":"Turbine 03 > Rotor","path":"aeronorth/windfarm_north/sector_a/turbine_03/rotor"}' | jq
```

## Step 4 — Create a signal via REST

```bash
curl -s -X POST http://localhost:8000/api/v1/signals \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": 5,
    "signal_type_id": 1,
    "name": "rpm",
    "display_name": "Rotor RPM",
    "unit": "rpm",
    "datatype": "float",
    "criticality": "buffered",
    "min_value": 0,
    "max_value": 25
  }' | jq
```

**Expected:** Response includes `"topic": "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm"` — topic is precomputed server-side. Client never supplied it.

## Step 5 — Verify topic in GET /api/v1/signals

```bash
curl http://localhost:8000/api/v1/signals | jq '.[0].topic'
# Must return: "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm"
```

## Step 6 — SQLAdmin UI

Open [http://localhost:8000/admin](http://localhost:8000/admin) in a browser.

1. Navigate to **Signals**.
2. You must see the rpm signal with the correct topic.
3. Create a new signal for `nacelle` cell (`asset_id` 6 if you created it, or create the nacelle asset first):
   - Asset: turbine_03/nacelle
   - Name: `wind_speed`, type informative, unit `m/s`, datatype float
4. After saving, confirm the topic is `aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed`.

## Step 7 — PATCH (update) a signal

```bash
curl -s -X PATCH http://localhost:8000/api/v1/signals/1 \
  -H "Content-Type: application/json" \
  -d '{"criticality": "critical"}' | jq '.criticality'
# Expected: "critical"
```

## Step 8 — Cold-start verification

```bash
docker compose down
docker compose up -d postgres api-service
curl http://localhost:8000/api/v1/signals | jq 'length'
# Must return same count as before — data persisted in postgres-data volume
```

## Step 9 — Alembic downgrade/upgrade cycle

```bash
docker compose exec api-service sh -c "
  alembic downgrade -1 &&
  alembic upgrade head
"
# Must complete without errors. Signals table returns to seeded state.
```

## Hito (hard gate from plan)

```bash
docker compose up -d postgres api-service
# Visit http://localhost:8000/admin in browser — log in, navigate to Signals
# Create a signal via SQLAdmin: asset turbine_03/rotor, name "rpm", informative, float, criticality "buffered"
# Then:
curl http://localhost:8000/api/v1/signals | jq
```

The created signal must appear with the precomputed topic `aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm`.

## Common issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` on port 8000 | api-service still starting | Wait for healthcheck, check `docker compose logs api-service` |
| `relation "asset_types" does not exist` | Alembic migration failed | Check logs for migration errors; run `docker compose exec api-service alembic upgrade head` manually |
| `404` on signal create | asset_id or signal_type_id wrong | List assets/signal-types first to get correct IDs |
| Topic field missing | Client is supplying topic in POST body | Remove `topic` from POST — it is computed server-side |
