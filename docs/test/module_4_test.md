# Module 4 Test Guide — UNS Registry and api-service

## What was built

- **`postgres`** service: PostgreSQL 16 registry database (port 5432).
- **`api-service`** (FastAPI): REST CRUD for assets, signals, asset types and signal types, plus SQLAdmin UI at `/admin`.
- **Alembic** migrations run on startup: `0001_initial` (schema + enums) + `0002_seed` (asset_type and signal_type rows).
- **`compute_topic()`** in `services/api-service/app/services/topic_builder.py` — the single authoritative implementation.

## Prerequisites

- Modules 1–3 hito passed (broker + simulator + Telegraf/TimescaleDB running).
- Docker and Docker Compose installed.
- `curl` available on the host (`jq` optional — commands below work without it).

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
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Step 2 — Verify seed data

```bash
curl -s http://localhost:8000/api/v1/asset-types
# Must return 10 entries: enterprise, wind_farm, sector, wind_turbine, rotor, nacelle, generator, gearbox, tower, controller

curl -s http://localhost:8000/api/v1/signal-types
# Must return 4 entries: informative, operational, descriptive, analytic
```

## Step 3 — Create the asset hierarchy via REST

Create the full ISA-95 path for turbine_03 bottom-up (parents before children):

```bash
# Enterprise
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"asset_type_id":1,"code":"aeronorth","display_name":"AeroNorth","path":"aeronorth"}'

# Site
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":1,"asset_type_id":2,"code":"windfarm_north","display_name":"Wind Farm North","path":"aeronorth/windfarm_north"}'

# Area
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":2,"asset_type_id":3,"code":"sector_a","display_name":"Sector A","path":"aeronorth/windfarm_north/sector_a"}'

# Line (turbine)
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":3,"asset_type_id":4,"code":"turbine_03","display_name":"Turbine 03","path":"aeronorth/windfarm_north/sector_a/turbine_03"}'

# Cell (rotor)
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":4,"asset_type_id":5,"code":"rotor","display_name":"Turbine 03 > Rotor","path":"aeronorth/windfarm_north/sector_a/turbine_03/rotor"}'
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
  }'
```

**Expected:** Response includes `"topic": "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm"` — topic is precomputed server-side. Client never supplied it.

## Step 5 — Verify topic in GET /api/v1/signals

```bash
curl -s http://localhost:8000/api/v1/signals
# In the output, .[0].topic must be: "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm"
```

## Step 6 — SQLAdmin UI

El objetivo de este paso es verificar que la UI de administración funciona y que el topic se computa correctamente también cuando se crea una señal desde la interfaz web (no solo desde la API).

### 6a — Verificar la señal rpm existente

1. Abre [http://localhost:8000/admin](http://localhost:8000/admin) en el navegador.
2. En el menú lateral izquierdo haz clic en **Signal** (o "Signals").
3. Verás la señal `rpm` creada en Step 4. Haz clic en ella para abrir el detalle.
4. Confirma que el campo **Topic** muestra exactamente:
   ```
   aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm
   ```
   Si el topic aparece vacío o incorrecto, hay un bug en `compute_topic()`.

### 6b — Crear el asset nacelle (ya creado via curl, asset_id=15)

El asset `nacelle` fue creado por curl con id=15. Puedes verificarlo en el menú **Asset** de SQLAdmin — debe aparecer con path `aeronorth/windfarm_north/sector_a/turbine_03/nacelle`.

Si por algún motivo no existe, créalo via curl antes de continuar:

```bash
curl -s -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"parent_id":11,"asset_type_id":6,"code":"nacelle","display_name":"Turbine 03 > Nacelle","path":"aeronorth/windfarm_north/sector_a/turbine_03/nacelle"}'
# Anota el "id" que devuelve — lo necesitas en el paso siguiente
```

### 6c — Crear la señal wind_speed desde SQLAdmin

1. En el menú lateral haz clic en **Signal**.
2. Haz clic en el botón **Create** (esquina superior derecha).
3. Rellena el formulario:
   - **Asset**: selecciona el que muestra `aeronorth/windfarm_north/sector_a/turbine_03/nacelle` (id=15)
   - **Signal type**: selecciona `informative`
   - **Name**: `wind_speed`
   - **Display name**: `Wind Speed`
   - **Unit**: `m/s`
   - **Datatype**: `float`
   - **Criticality**: `buffered`
   - Deja el resto vacío o con sus valores por defecto
4. Haz clic en **Save**.

### 6d — Confirmar el topic

Después de guardar, SQLAdmin te redirige a la lista de señales. Haz clic en `wind_speed` para abrir el detalle.

El campo **Topic** debe mostrar exactamente:
```
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed
```

También puedes verificarlo via curl:

```bash
curl -s http://localhost:8000/api/v1/signals
# Busca el objeto con "name":"wind_speed" y confirma su "topic"
```

## Step 7 — PATCH (update) a signal

```bash
curl -s -X PATCH http://localhost:8000/api/v1/signals/1 \
  -H "Content-Type: application/json" \
  -d '{"criticality": "critical"}'
# Expected: response contains "criticality":"critical"
```

## Step 8 — Cold-start verification

```bash
docker compose down
docker compose up -d postgres api-service
curl -s http://localhost:8000/api/v1/signals
# Must return the same signals as before — data persisted in postgres-data volume
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
curl -s http://localhost:8000/api/v1/signals
```

The created signal must appear with the precomputed topic `aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm`.

## Common issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` on port 8000 | api-service still starting | Wait for healthcheck, check `docker compose logs api-service` |
| `relation "asset_types" does not exist` | Alembic migration failed | Check logs for migration errors; run `docker compose exec api-service alembic upgrade head` manually |
| `404` on signal create | asset_id or signal_type_id wrong | List assets/signal-types first to get correct IDs |
| Topic field missing | Client is supplying topic in POST body | Remove `topic` from POST — it is computed server-side |
