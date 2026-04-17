# Module 2 Test Guide — Simulator and ISA-95 Hierarchy

This guide verifies the Module 2 hito: the `simulator` service publishes synthetic telemetry for one turbine using ISA-95 topics, with valid JSON payloads arriving every 10 seconds.

---

## Prerequisites

- Module 1 hito passed (EMQX broker healthy, pub/sub verified)
- Docker and Docker Compose installed
- Python 3.12 with `paho-mqtt` and `python-dotenv` installed (for automated scripts)

---

## Automated test scripts

All tests have automated Python scripts in `scripts/M2_Test/`. Run them from the **project root**:

```bash
python scripts/M2_Test/M2_T1.py
python scripts/M2_Test/M2_T2.py
python scripts/M2_Test/M2_T3.py   # HITO — waits ~30 s
python scripts/M2_Test/M2_T4.py   # waits ~70 s
python scripts/M2_Test/M2_T5.py
python scripts/M2_Test/M2_T6.py   # waits ~30 s
python scripts/M2_Test/M2_T7.py
```

Each script prints `[PASS]` or `[FAIL]` per check and exits with code `0` (all pass) or `1` (any fail).

---

## T1 — Build and start the simulator

**Automated:** `python scripts/M2_Test/M2_T1.py`

Manual equivalent:

```bash
docker compose up -d --build mqtt-broker simulator
docker compose ps
```

Expected output:

```
NAME                      STATUS
aeronorth-mqtt-broker     Up (healthy)
aeronorth-simulator       Up
```

---

## T2 — Simulator logs show published messages

**Automated:** `python scripts/M2_Test/M2_T2.py`

Manual equivalent:

```bash
docker compose logs simulator
```

Expected: structured log lines like:

```
{"event": "simulator.starting", "asset_path": "aeronorth/windfarm_north/sector_a/turbine_03", "interval_ms": 10000}
{"event": "simulator.connected", "host": "mqtt-broker", "port": 1883}
{"event": "simulator.published", "topic": "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm", "val": 12.43, "ts": 1713264000000}
{"event": "simulator.published", "topic": "aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed", "val": 14.21, "ts": ...}
{"event": "simulator.published", "topic": "aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power", "val": 856.7, "ts": ...}
```

---

## T3 — HITO: Subscribe and verify 3 topics tick every 10 seconds

**Automated:** `python scripts/M2_Test/M2_T3.py`

The script subscribes, validates each payload, counts 3 complete cycles, and prints `[PASS] T3 HITO` when done.

Manual equivalent:

```bash
mosquitto_sub -h localhost -p 1883 \
  -u testuser -P testpass \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/+/measure/#' -v
```

Wait at least 30 seconds. Expected — 3 messages per cycle, repeating every ~10 s:

```
aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm {"val":12.43,"ts":1713264000000,"q":1}
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed {"val":14.21,"ts":1713264000012,"q":1}
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power {"val":856.7,"ts":1713264000025,"q":1}
```

**Hito passes when:**
- All 3 topics appear
- Each payload is valid JSON with keys `val`, `ts`, `q`
- `q` is always `1`
- `ts` is a 13-digit Unix millisecond timestamp
- Messages repeat every ~10 seconds for at least 3 cycles

---

## T4 — Values change over time (sine wave)

**Automated:** `python scripts/M2_Test/M2_T4.py`

The script collects `rpm` samples for 70 seconds and asserts that `min != max`.

Manual equivalent: wait 60 seconds and observe that `rpm` values oscillate (0–20 range), confirming the sine wave generator is working and not stuck at a constant value.

---

## T5 — No retained messages on measure topics

**Automated:** `python scripts/M2_Test/M2_T5.py`

The script stops the simulator, connects a fresh subscriber, waits 5 s for retained messages, asserts none arrive, then restarts the simulator.

Manual equivalent:

```bash
docker compose stop simulator

mosquitto_sub -h localhost -p 1883 -u testuser -P testpass \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/+/measure/#' -v \
  --retained-only
```

Expected: **no messages received** (measure topics must never use `retain=True`).

---

## T6 — Configurable interval

**Automated:** `python scripts/M2_Test/M2_T6.py`

The script relaunches the simulator with `SIM_INTERVAL_MS=3000`, measures the inter-message interval (asserts < 5 s), then restores the default.

Manual equivalent:

```bash
SIM_INTERVAL_MS=3000 docker compose up -d --build simulator

mosquitto_sub -h localhost -p 1883 -u testuser -P testpass \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/+/measure/#' -v
```

Expected: messages arrive every ~3 seconds instead of 10.

Reset to default:

```bash
docker compose up -d simulator
```

---

## T7 — Compose config is valid

**Automated:** `python scripts/M2_Test/M2_T7.py`

Manual equivalent:

```bash
docker compose config
```

Expected: prints merged config with no errors. Both `mqtt-broker` and `simulator` services appear, `simulator` shows `depends_on: mqtt-broker`.

---

## Summary

| Test | Script | What it checks | Pass condition |
|------|--------|---------------|----------------|
| T1 | `M2_T1.py` | Containers start | Both `Up`, broker `healthy` |
| T2 | `M2_T2.py` | Structlog output | 3 published events per cycle |
| T3 | `M2_T3.py` | **HITO** — 3 topics, valid JSON | All 3 topics tick for 3+ cycles |
| T4 | `M2_T4.py` | Sine wave changes | `rpm` oscillates, not constant |
| T5 | `M2_T5.py` | No retained messages | Empty response from `--retained-only` |
| T6 | `M2_T6.py` | Configurable interval | 3 s interval with env override |
| T7 | `M2_T7.py` | Compose validity | `docker compose config` clean |
