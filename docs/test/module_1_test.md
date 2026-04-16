# Module 1 test guide — Broker and first messages

Verifies the deliverables from Module 1 in [docs/plan/recursive-tickling-oasis.md](../plan/recursive-tickling-oasis.md).

## Prerequisites

- Docker Desktop running.
- Python 3.12 and Poetry installed.
- Poetry virtualenv set up at the project root:
  ```bash
  poetry install
  ```
- EMQX MQTT user created (one-time setup — see below).

### One-time EMQX user setup

The EMQX broker requires authentication. Create the `testuser` account before running T3–T7:

```bash
# 1. Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:18083/api/v5/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"public123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 2. Create the built-in database authenticator (if not already present)
curl -s -X POST http://localhost:18083/api/v5/authentication \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mechanism":"password_based","backend":"built_in_database","user_id_type":"username"}'

```
1. Ejecuta este Paso 2 corregido:
Copia y pega este comando en tu terminal WSL (donde el $TOKEN todavía está guardado en la memoria):

Bash
```
curl -s -X POST http://localhost:18083/api/v5/authentication \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mechanism":"password_based","backend":"built_in_database","user_id_type":"username","password_hash_algorithm":{"name":"sha256","salt_position":"suffix"}}'
```


```




# 3. Create the test user
curl -s -X POST "http://localhost:18083/api/v5/authentication/password_based:built_in_database/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"testuser","password":"testpass"}'
```

Credentials are stored in `.env` (already present at project root):
```
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=testuser
MQTT_PASSWORD=testpass
```

---

## T1 — Container starts and is healthy

```bash
docker compose up -d mqtt-broker
docker compose ps mqtt-broker
```

**Expected:** `STATUS` column shows `healthy` (not `starting` or `unhealthy`). May take ~20 s for the first run while EMQX initialises.

---

## T2 — Dashboard is reachable

Open `http://localhost:18083` in a browser.

**Expected:** EMQX dashboard login page loads. Log in with `admin` / `public123`. The dashboard home shows the broker running.

---

## T3 — Basic publish / subscribe

Open **two terminals** at the project root.

**Terminal A — subscriber:**
```bash
poetry run python scripts/t3_sub.py
```

**Terminal B — publisher:**
```bash
poetry run python scripts/t3_pub.py
```

**Expected:** Terminal A prints:
```
demo/hello {"val":1}
```
Terminal B prints:
```
[OK] Published to demo/hello
```

Stop Terminal A with `Ctrl+C`.

---

## T4 — Retained message survives subscriber restart

**Terminal B — publish with retain flag:**
```bash
poetry run python scripts/t4_pub.py
```
Expected output: `[OK] Retained message published to demo/retained`

**Terminal A — first subscriber:**
```bash
poetry run python scripts/t4_sub.py
```
Message `demo/retained {"val":42}` must arrive immediately on connect (no new publish needed).

**Stop Terminal A** (`Ctrl+C`), then restart the subscriber:
```bash
poetry run python scripts/t4_sub.py
```

**Expected:** The retained message arrives again on reconnect, without Terminal B publishing anything new.

---

## T5 — Clear a retained message

```bash
poetry run python scripts/t5_clear_retained.py
```

**Expected:**
```
[PASS] Retained message cleared
```

If the retained message from T4 is still present it prints `[FAIL]` — re-run after confirming T4 published correctly.

---

## T6 — Wildcard patterns work

Open **two terminals** at the project root.

**Terminal A — subscriber:**
```bash
poetry run python scripts/t6_sub.py
```

**Terminal B — publisher:**
```bash
poetry run python scripts/t6_pub.py
```

**Expected:** Terminal A prints all three messages:
```
aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm {"val":120}
aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed {"val":8.5}
aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power {"val":2100}
```

Stop Terminal A with `Ctrl+C`.

---

## T7 — Cold start (data persists across container restart)

Run from the project root (the script uses `docker compose` internally):

```bash
poetry run python scripts/t7_cold_start.py
```

The script:
1. Publishes `{"val":99}` to `demo/persist` with `retain=True`.
2. Restarts the `mqtt-broker` container via `docker compose restart`.
3. Polls every 3 s until the container is `healthy` (up to 60 s).
4. Subscribes to `demo/persist` and waits for the retained message.

**Expected:**
```
[PASS] Retained message survived container restart
```

---

## T8 — Compose config is valid

```bash
docker compose config --quiet
```

**Expected:** No output, exit code 0.

---

## Hito gate checklist

All of the following must be true before closing Module 1:

- [x] T1: `mqtt-broker` container reports `healthy`
- [x] T2: EMQX dashboard loads at `http://localhost:18083`
- [x] T3: Basic pub/sub works
- [x] T4: Retained message arrives on subscriber reconnect
- [x] T5: Retained message can be cleared with an empty payload
- [x] T6: `+` and `#` wildcards match as expected
- [x] T7: Retained messages survive a container restart (volume persisted)
- [x] T8: `docker compose config` exits cleanly

Once all boxes are checked, Jorge writes `docs/es/10-modulo-01-broker.md` and then Module 2 begins.
