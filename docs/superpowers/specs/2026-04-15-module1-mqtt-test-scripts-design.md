# Design: Module 1 MQTT Test Scripts

**Date:** 2026-04-15
**Scope:** Python scripts to execute tests T3–T7 from `docs/test/module_1_test.md` without requiring `mosquitto_pub`/`mosquitto_sub` on PATH.

---

## Context

Module 1 tests verify the EMQX broker running in Docker. Tests T1 and T2 are already passing (container healthy, dashboard reachable). Tests T3–T7 require MQTT publish/subscribe operations. Rather than depending on `mosquitto-clients` being installed on the host, we implement these tests as Python scripts.

EMQX 5.x requires authentication by default. Credentials are read from the project `.env` file.

---

## Architecture

### Dependency management

- **Poetry** `pyproject.toml` at the project root manages all Python dependencies.
- Single virtualenv for the entire project (scripts + future services share the same toolchain).
- Runtime dependency: `paho-mqtt>=2.0`.
- Dev dependencies: none beyond what the project already uses.

### File layout

```
(project root)
├── pyproject.toml         # Poetry project file
├── poetry.lock
├── .env                   # MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD
scripts/
├── mqtt_helper.py         # Shared connection helper
├── t3_sub.py              # T3 subscriber
├── t3_pub.py              # T3 publisher
├── t4_sub.py              # T4 subscriber (retained message on connect)
├── t4_pub.py              # T4 publisher with retain=True
├── t5_clear_retained.py   # T5 clear retained (publisher + verify)
├── t6_sub.py              # T6 subscriber with wildcard
├── t6_pub.py              # T6 publisher (3 turbine messages)
└── t7_cold_start.py       # T7 full flow: publish → restart → verify retained
```

---

## `mqtt_helper.py`

Reads from `.env` (via `python-dotenv`):

| Variable       | Default       | Description              |
|----------------|---------------|--------------------------|
| `MQTT_HOST`    | `localhost`   | Broker hostname          |
| `MQTT_PORT`    | `1883`        | Broker port              |
| `MQTT_USER`    | *(required)*  | MQTT username            |
| `MQTT_PASSWORD`| *(required)*  | MQTT password            |

Public API:

```python
connect(client_id: str | None = None) -> paho.mqtt.client.Client
# Returns a connected, authenticated paho Client. Caller is responsible for disconnect.

publish(topic: str, payload: str | None, retain: bool = False) -> None
# One-shot: connect, publish, disconnect.

subscribe(topic: str, timeout: float = 5.0, count: int = 1) -> list[tuple[str, str]]
# Connects, waits up to `timeout` seconds for `count` messages, returns list of (topic, payload).
# Returns fewer items than count if timeout is reached.
```

All functions raise `ConnectionError` on auth failure or broker unreachable, with a clear message.

---

## Individual scripts

### T3 — Basic pub/sub

**`t3_sub.py`**
Subscribes to `demo/#`. Prints each received message as `<topic> <payload>`. Runs until Ctrl+C.

**`t3_pub.py`**
Publishes `{"val":1}` to `demo/hello`. Prints `[OK] Published to demo/hello`.

Expected workflow: start `t3_sub.py` in terminal A, run `t3_pub.py` in terminal B, see message appear in A.

---

### T4 — Retained message survives reconnect

**`t4_pub.py`**
Publishes `{"val":42}` to `demo/retained` with `retain=True`. Prints `[OK] Retained message published`.

**`t4_sub.py`**
Subscribes to `demo/#`. Prints each received message. On connect, the retained message must arrive immediately (no new publish needed). Runs until Ctrl+C.

Expected workflow: run `t4_pub.py` once, then run `t4_sub.py` twice (stopping with Ctrl+C between runs) — retained message must appear both times.

---

### T5 — Clear retained message

**`t5_clear_retained.py`**
1. Publishes empty payload (`None`) with `retain=True` to `demo/retained` — this clears the retained message.
2. Subscribes to `demo/retained` for 3 seconds.
3. If no message arrives: prints `[PASS] Retained message cleared`.
4. If a message arrives: prints `[FAIL] Retained message still present: <payload>`.

---

### T6 — Wildcard patterns

**`t6_pub.py`**
Publishes three messages using real project topic paths:
- `aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm` → `{"val":120}`
- `aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed` → `{"val":8.5}`
- `aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power` → `{"val":2100}`

**`t6_sub.py`**
Subscribes to `aeronorth/+/+/+/+/measure/#`. Prints each received message. Runs until Ctrl+C.

Expected workflow: start `t6_sub.py`, then run `t6_pub.py` — all 3 messages must appear.

---

### T7 — Cold start (retained persists across restart)

**`t7_cold_start.py`** (single script, sequential flow)

1. Publishes `{"val":99}` to `demo/persist` with `retain=True`.
2. Runs `docker compose restart mqtt-broker` via `subprocess`.
3. Polls `docker compose ps mqtt-broker` every 3s until `(healthy)` appears or 60s timeout.
4. Subscribes to `demo/persist` for 5 seconds.
5. If message `{"val":99}` arrives: prints `[PASS] Retained message survived container restart`.
6. If not: prints `[FAIL] Retained message lost after restart`.

Must be run from the project root (where `docker-compose.yml` lives) so `docker compose` commands resolve correctly.

---

## `.env` setup

The `.env` file must contain MQTT credentials. If no `.env` exists yet, create it:

```env
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=testuser
MQTT_PASSWORD=testpass
```

The user must also create the `testuser` account in EMQX before running the scripts:

```bash
curl -u admin:public -X POST http://localhost:18083/api/v5/authentication/password_based:built_in_database/users \
  -H "Content-Type: application/json" \
  -d '{"user_id": "testuser", "password": "testpass"}'
```

---

## Poetry setup

```toml
[tool.poetry]
name = "aeronorth-uns"
version = "0.1.0"
description = "AeroNorth UNS platform"
python = "^3.12"

[tool.poetry.dependencies]
python = "^3.12"
paho-mqtt = "^2.0"
python-dotenv = "^1.0"
```

Run once to create the virtualenv:
```bash
poetry install
```

Run scripts with:
```bash
poetry run python scripts/t3_sub.py
```

---

## Out of scope

- No test runner or orchestration — each script is run manually.
- No assertions library — pass/fail is printed to stdout.
- No CI integration — these are interactive verification scripts, not automated tests.
