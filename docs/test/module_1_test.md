# Module 1 test guide — Broker and first messages

Verifies the deliverables from Module 1 in [docs/plan/recursive-tickling-oasis.md](../plan/recursive-tickling-oasis.md).

## Prerequisites

- Docker Desktop running.
- `mosquitto-clients` installed on the host (`mosquitto_pub` / `mosquitto_sub` available on PATH).
  - Windows: `winget install EclipseFoundation.Mosquitto`
  - macOS: `brew install mosquitto`
  - Ubuntu/Debian: `sudo apt install mosquitto-clients`

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

**Expected:** EMQX dashboard login page loads. Log in with the credentials from your `.env` (default `admin` / `public`). The dashboard home shows the broker running.

---

## T3 — Basic publish / subscribe

Open **two terminals**.

**Terminal A — subscriber:**
```bash
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -v
```

**Terminal B — publisher:**
```bash
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -m '{"val":1}'
```

**Expected:** Terminal A prints:
```
demo/hello {"val":1}
```

---

## T4 — Retained message survives subscriber restart

**Terminal B — publish with retain flag:**
```bash
mosquitto_pub -h localhost -p 1883 -t 'demo/retained' -m '{"val":42}' -r
```

**Terminal A — first subscriber (already running or start fresh):**
```bash
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -v
```
Message `demo/retained {"val":42}` must arrive immediately on connect.

**Stop Terminal A** (`Ctrl+C`), then restart the subscriber:
```bash
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -v
```

**Expected:** The retained message arrives again on reconnect, without Terminal B publishing anything new.

---

## T5 — Clear a retained message

```bash
mosquitto_pub -h localhost -p 1883 -t 'demo/retained' -r -n
```

Restart Terminal A subscriber.

**Expected:** No message arrives for `demo/retained` — the retained message has been cleared.

---

## T6 — Wildcard patterns work

```bash
# Publish three messages
mosquitto_pub -h localhost -p 1883 -t 'aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm' -m '{"val":120}'
mosquitto_pub -h localhost -p 1883 -t 'aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed' -m '{"val":8.5}'
mosquitto_pub -h localhost -p 1883 -t 'aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power' -m '{"val":2100}'

# Subscribe with + wildcard
mosquitto_sub -h localhost -p 1883 -t 'aeronorth/+/+/+/+/measure/#' -v
```

Run the three publishes again while the subscriber is active.

**Expected:** All three messages appear. No messages for topics that don't match the pattern.

---

## T7 — Cold start (data persists across container restart)

```bash
mosquitto_pub -h localhost -p 1883 -t 'demo/persist' -m '{"val":99}' -r
docker compose restart mqtt-broker
# Wait for healthy
docker compose ps mqtt-broker
mosquitto_sub -h localhost -p 1883 -t 'demo/persist' -v
```

**Expected:** `demo/persist {"val":99}` arrives immediately after reconnect, proving the EMQX named volume (`emqx-data`) persists retained messages across restarts.

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
