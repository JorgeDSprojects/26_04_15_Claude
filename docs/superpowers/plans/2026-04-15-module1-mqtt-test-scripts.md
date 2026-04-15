# Module 1 MQTT Test Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create Python scripts in `scripts/` to execute Module 1 tests T3–T7 against the EMQX broker running in Docker, using credentials from `.env`.

**Architecture:** A shared `mqtt_helper.py` module reads credentials from `.env` and provides `connect()`, `publish()`, and `subscribe()` functions using `paho-mqtt`. Individual test scripts import the helper and implement each test scenario as an independent, runnable file. Subscriber and publisher scripts are separated where both are needed.

**Tech Stack:** Python 3.12, paho-mqtt 2.x, python-dotenv 1.x, Poetry for dependency management.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Create | Poetry project config, declares `paho-mqtt` and `python-dotenv` deps |
| `.env` | Create | MQTT credentials for local dev |
| `scripts/mqtt_helper.py` | Create | `connect()`, `publish()`, `subscribe()` — reads `.env` |
| `scripts/t3_sub.py` | Create | T3: subscribe to `demo/#`, print messages, loop until Ctrl+C |
| `scripts/t3_pub.py` | Create | T3: publish `{"val":1}` to `demo/hello` |
| `scripts/t4_pub.py` | Create | T4: publish `{"val":42}` to `demo/retained` with retain=True |
| `scripts/t4_sub.py` | Create | T4: subscribe to `demo/#`, print messages, loop until Ctrl+C |
| `scripts/t5_clear_retained.py` | Create | T5: clear retained on `demo/retained`, verify nothing arrives |
| `scripts/t6_pub.py` | Create | T6: publish 3 turbine messages |
| `scripts/t6_sub.py` | Create | T6: subscribe to `aeronorth/+/+/+/+/measure/#`, loop until Ctrl+C |
| `scripts/t7_cold_start.py` | Create | T7: pub retained → restart broker → verify retained survives |

---

## Task 1: Create MQTT user in EMQX and `.env` file

**Files:**
- Create: `.env`

- [ ] **Step 1: Create the MQTT user in EMQX via REST API**

Run this from any terminal (broker must be running):

```bash
curl -u admin:public -X POST http://localhost:18083/api/v5/authentication/password_based:built_in_database/users \
  -H "Content-Type: application/json" \
  -d '{"user_id": "testuser", "password": "testpass"}'
```

Expected output:
```json
{"user_id":"testuser","is_superuser":false}
```

If you get `404`, the built-in database authenticator may not be enabled. In that case open the EMQX dashboard at `http://localhost:18083`, go to **Access Control → Authentication**, enable the "Password-Based / Built-in Database" authenticator, then retry.

- [ ] **Step 2: Create `.env` at the project root**

Create the file `g:\00_data\00_Formacion\SA_projects\UNS\26_04_15_Claude\.env` with this content:

```env
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=testuser
MQTT_PASSWORD=testpass
```

- [ ] **Step 3: Verify the user can connect**

```bash
curl -u admin:public http://localhost:18083/api/v5/authentication/password_based:built_in_database/users/testuser
```

Expected: `{"user_id":"testuser","is_superuser":false}`

---

## Task 2: Set up Poetry and install dependencies

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Verify Poetry is installed**

```bash
poetry --version
```

Expected: `Poetry (version 1.x.x)` or `2.x.x`. If not found, install from `https://python-poetry.org/docs/#installation`.

- [ ] **Step 2: Create `pyproject.toml` at the project root**

Create `g:\00_data\00_Formacion\SA_projects\UNS\26_04_15_Claude\pyproject.toml`:

```toml
[tool.poetry]
name = "aeronorth-uns"
version = "0.1.0"
description = "AeroNorth UNS — Unified Namespace platform"
authors = []
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.12"
paho-mqtt = "^2.0"
python-dotenv = "^1.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 3: Install dependencies**

From the project root:

```bash
poetry install
```

Expected: Poetry creates a virtualenv and installs `paho-mqtt` and `python-dotenv`. Last line should say something like `Installing the current project: aeronorth-uns (0.1.0)`.

- [ ] **Step 4: Verify packages are available**

```bash
poetry run python -c "import paho.mqtt.client; import dotenv; print('OK')"
```

Expected: `OK`

---

## Task 3: Create `scripts/mqtt_helper.py`

**Files:**
- Create: `scripts/mqtt_helper.py`

- [ ] **Step 1: Create the `scripts/` directory and `mqtt_helper.py`**

Create `g:\00_data\00_Formacion\SA_projects\UNS\26_04_15_Claude\scripts\mqtt_helper.py`:

```python
"""
Shared MQTT helper for test scripts.
Reads broker credentials from .env in the project root.
"""
import os
import time
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USER = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASSWORD")


def connect(client_id: str | None = None) -> mqtt.Client:
    """Return a connected, authenticated paho Client.
    Caller is responsible for calling client.disconnect()."""
    if not USER or not PASSWORD:
        raise ConnectionError(
            "MQTT_USER and MQTT_PASSWORD must be set in .env"
        )
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id or "",
    )
    client.username_pw_set(USER, PASSWORD)

    connected = {"rc": None}

    def on_connect(c, userdata, flags, reason_code, properties):
        connected["rc"] = reason_code.value if hasattr(reason_code, "value") else int(reason_code)

    client.on_connect = on_connect
    client.connect(HOST, PORT, keepalive=60)
    client.loop_start()

    deadline = time.time() + 10
    while connected["rc"] is None and time.time() < deadline:
        time.sleep(0.05)
    client.loop_stop()

    if connected["rc"] is None:
        raise ConnectionError(f"Timed out connecting to {HOST}:{PORT}")
    if connected["rc"] != 0:
        raise ConnectionError(
            f"Connection refused by broker (rc={connected['rc']}). "
            "Check MQTT_USER / MQTT_PASSWORD in .env."
        )
    return client


def publish(topic: str, payload: str | None, retain: bool = False) -> None:
    """One-shot: connect, publish, disconnect."""
    client = connect()
    client.loop_start()
    info = client.publish(topic, payload, qos=0, retain=retain)
    info.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()


def subscribe(
    topic: str, timeout: float = 5.0, count: int = 1
) -> list[tuple[str, str]]:
    """Connect, wait up to `timeout` seconds for `count` messages.
    Returns list of (topic, payload) tuples. May return fewer than count."""
    messages: list[tuple[str, str]] = []
    done = {"flag": False}

    client = connect()

    def on_message(c, userdata, msg):
        messages.append((msg.topic, msg.payload.decode("utf-8", errors="replace")))
        if len(messages) >= count:
            done["flag"] = True

    client.on_message = on_message
    client.subscribe(topic, qos=0)
    client.loop_start()

    deadline = time.time() + timeout
    while not done["flag"] and time.time() < deadline:
        time.sleep(0.05)

    client.loop_stop()
    client.disconnect()
    return messages
```

- [ ] **Step 2: Verify the helper connects to the broker**

```bash
poetry run python -c "from scripts.mqtt_helper import connect; c = connect(); print('Connected'); c.disconnect()"
```

Expected: `Connected`

If you get `ConnectionError: Connection refused by broker (rc=4)` or `rc=5`, the credentials are wrong — check `.env` and the EMQX user created in Task 1.

---

## Task 4: Create T3 scripts — Basic pub/sub

**Files:**
- Create: `scripts/t3_sub.py`
- Create: `scripts/t3_pub.py`

- [ ] **Step 1: Create `scripts/t3_sub.py`**

```python
"""T3 subscriber — subscribes to demo/# and prints all messages.
Run in Terminal A, then run t3_pub.py in Terminal B.
Stop with Ctrl+C."""
import paho.mqtt.client as mqtt
from scripts.mqtt_helper import connect

client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe("demo/#", qos=0)
print("Subscribed to demo/# — waiting for messages (Ctrl+C to stop)...")
client.loop_forever()
```

- [ ] **Step 2: Create `scripts/t3_pub.py`**

```python
"""T3 publisher — publishes {"val":1} to demo/hello.
Run in Terminal B while t3_sub.py is running in Terminal A."""
from scripts.mqtt_helper import publish

publish("demo/hello", '{"val":1}')
print("[OK] Published to demo/hello")
```

- [ ] **Step 3: Run T3 — open two terminals**

Terminal A:
```bash
poetry run python scripts/t3_sub.py
```
Expected: `Subscribed to demo/# — waiting for messages (Ctrl+C to stop)...`

Terminal B:
```bash
poetry run python scripts/t3_pub.py
```
Expected in Terminal B: `[OK] Published to demo/hello`

Expected in Terminal A: `demo/hello {"val":1}`

Stop Terminal A with Ctrl+C. T3 PASS.

---

## Task 5: Create T4 scripts — Retained message survives reconnect

**Files:**
- Create: `scripts/t4_pub.py`
- Create: `scripts/t4_sub.py`

- [ ] **Step 1: Create `scripts/t4_pub.py`**

```python
"""T4 publisher — publishes {"val":42} to demo/retained with retain=True.
Run once. The broker stores the message for future subscribers."""
from scripts.mqtt_helper import publish

publish("demo/retained", '{"val":42}', retain=True)
print("[OK] Retained message published to demo/retained")
```

- [ ] **Step 2: Create `scripts/t4_sub.py`**

```python
"""T4 subscriber — subscribes to demo/# and prints all messages.
The retained message must arrive immediately on connect (no new publish needed).
Run twice (Ctrl+C between runs) to verify retained message arrives both times."""
import paho.mqtt.client as mqtt
from scripts.mqtt_helper import connect

client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe("demo/#", qos=0)
print("Subscribed to demo/# — retained message should appear immediately (Ctrl+C to stop)...")
client.loop_forever()
```

- [ ] **Step 3: Run T4**

First, publish the retained message:
```bash
poetry run python scripts/t4_pub.py
```
Expected: `[OK] Retained message published to demo/retained`

First subscriber run:
```bash
poetry run python scripts/t4_sub.py
```
Expected: `demo/retained {"val":42}` appears immediately on connect.

Stop with Ctrl+C. Start again:
```bash
poetry run python scripts/t4_sub.py
```
Expected: `demo/retained {"val":42}` appears again immediately — no new publish needed. T4 PASS.

---

## Task 6: Create T5 script — Clear retained message

**Files:**
- Create: `scripts/t5_clear_retained.py`

- [ ] **Step 1: Create `scripts/t5_clear_retained.py`**

```python
"""T5 — clears the retained message on demo/retained, then verifies nothing arrives.
Publishes an empty payload with retain=True (MQTT spec: empty retained = delete).
Expected output: [PASS] Retained message cleared."""
from scripts.mqtt_helper import publish, subscribe

# Clear the retained message: empty payload + retain=True
publish("demo/retained", None, retain=True)
print("Sent empty retained payload to demo/retained — clearing retained message...")

# Wait 3 seconds for any retained message to arrive
messages = subscribe("demo/retained", timeout=3.0, count=1)

if not messages:
    print("[PASS] Retained message cleared — nothing arrived in 3s")
else:
    payload = messages[0][1]
    print(f"[FAIL] Retained message still present: {payload}")
```

- [ ] **Step 2: Run T5**

```bash
poetry run python scripts/t5_clear_retained.py
```

Expected:
```
Sent empty retained payload to demo/retained — clearing retained message...
[PASS] Retained message cleared — nothing arrived in 3s
```

If you see `[FAIL]`, the retained message was not cleared. Verify the broker is receiving the empty payload by checking EMQX dashboard under Topics. T5 PASS.

---

## Task 7: Create T6 scripts — Wildcard patterns

**Files:**
- Create: `scripts/t6_pub.py`
- Create: `scripts/t6_sub.py`

- [ ] **Step 1: Create `scripts/t6_pub.py`**

```python
"""T6 publisher — publishes 3 turbine measurement messages using real project topic paths."""
from scripts.mqtt_helper import publish

messages = [
    ("aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm",          '{"val":120}'),
    ("aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed",  '{"val":8.5}'),
    ("aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power", '{"val":2100}'),
]

for topic, payload in messages:
    publish(topic, payload)
    print(f"[OK] Published to {topic}")
```

- [ ] **Step 2: Create `scripts/t6_sub.py`**

```python
"""T6 subscriber — subscribes to aeronorth/+/+/+/+/measure/# (single-level wildcards).
Run in Terminal A, then run t6_pub.py in Terminal B.
All 3 turbine messages must appear. Stop with Ctrl+C."""
from scripts.mqtt_helper import connect

PATTERN = "aeronorth/+/+/+/+/measure/#"
client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe(PATTERN, qos=0)
print(f"Subscribed to {PATTERN} — waiting for messages (Ctrl+C to stop)...")
client.loop_forever()
```

- [ ] **Step 3: Run T6 — open two terminals**

Terminal A:
```bash
poetry run python scripts/t6_sub.py
```
Expected: `Subscribed to aeronorth/+/+/+/+/measure/# — waiting for messages (Ctrl+C to stop)...`

Terminal B:
```bash
poetry run python scripts/t6_pub.py
```
Expected in Terminal B:
```
[OK] Published to aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm
[OK] Published to aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed
[OK] Published to aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power
```

Expected in Terminal A (all 3 lines):
```
aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm {"val":120}
aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed {"val":8.5}
aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power {"val":2100}
```

Stop Terminal A with Ctrl+C. T6 PASS.

---

## Task 8: Create T7 script — Cold start

**Files:**
- Create: `scripts/t7_cold_start.py`

- [ ] **Step 1: Create `scripts/t7_cold_start.py`**

```python
"""T7 cold start — verifies that retained messages survive a container restart.
Must be run from the project root (where docker-compose.yml lives).
Flow: publish retained → restart mqtt-broker → wait for healthy → verify retained arrives."""
import subprocess
import sys
import time
from scripts.mqtt_helper import publish, subscribe


def wait_for_healthy(timeout: int = 60) -> bool:
    """Poll docker compose ps until mqtt-broker shows (healthy). Returns True if healthy within timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "compose", "ps", "mqtt-broker"],
            capture_output=True, text=True
        )
        if "(healthy)" in result.stdout:
            return True
        time.sleep(3)
    return False


# Step 1: Publish retained message
print("Publishing retained message to demo/persist...")
publish("demo/persist", '{"val":99}', retain=True)
print("[OK] Retained message published")

# Step 2: Restart the broker
print("Restarting mqtt-broker container...")
subprocess.run(["docker", "compose", "restart", "mqtt-broker"], check=True)
print("[OK] Restart command issued — waiting for broker to become healthy...")

# Step 3: Wait for healthy
if not wait_for_healthy(timeout=60):
    print("[FAIL] Broker did not become healthy within 60s")
    sys.exit(1)
print("[OK] Broker is healthy")

# Step 4: Subscribe and check for retained message
print("Subscribing to demo/persist — waiting up to 5s for retained message...")
messages = subscribe("demo/persist", timeout=5.0, count=1)

if messages and messages[0][1] == '{"val":99}':
    print('[PASS] Retained message survived container restart: demo/persist {"val":99}')
elif messages:
    print(f"[FAIL] Unexpected payload received: {messages[0][1]}")
    sys.exit(1)
else:
    print("[FAIL] No message received — retained message was lost after restart")
    sys.exit(1)
```

- [ ] **Step 2: Run T7 from the project root**

```bash
poetry run python scripts/t7_cold_start.py
```

Expected output:
```
Publishing retained message to demo/persist...
[OK] Retained message published
Restarting mqtt-broker container...
[OK] Restart command issued — waiting for broker to become healthy...
[OK] Broker is healthy
Subscribing to demo/persist — waiting up to 5s for retained message...
[PASS] Retained message survived container restart: demo/persist {"val":99}
```

If `[FAIL] Broker did not become healthy within 60s`, check `docker compose logs mqtt-broker`. T7 PASS.

---

## Task 9: Final verification and checklist update

- [ ] **Step 1: Run T3 one more time end-to-end to confirm everything works together**

Terminal A: `poetry run python scripts/t3_sub.py`
Terminal B: `poetry run python scripts/t3_pub.py`

Confirm `demo/hello {"val":1}` appears in Terminal A.

- [ ] **Step 2: Update the hito checklist in `docs/test/module_1_test.md`**

Change the checklist from:
```markdown
- [ ] T3: Basic pub/sub works
- [ ] T4: Retained message arrives on subscriber reconnect
- [ ] T5: Retained message can be cleared with an empty payload
- [ ] T6: `+` and `#` wildcards match as expected
- [ ] T7: Retained messages survive a container restart (volume persisted)
```

To:
```markdown
- [x] T3: Basic pub/sub works
- [x] T4: Retained message arrives on subscriber reconnect
- [x] T5: Retained message can be cleared with an empty payload
- [x] T6: `+` and `#` wildcards match as expected
- [x] T7: Retained messages survive a container restart (volume persisted)
```

- [ ] **Step 3: Run T8 (docker compose config check)**

```bash
docker compose config --quiet
```

Expected: no output, exit code 0. If exit code is non-zero, check `docker-compose.yml` for syntax errors.

Update checklist:
```markdown
- [x] T8: `docker compose config` exits cleanly
```

- [ ] **Step 4: Commit everything**

```bash
git add pyproject.toml poetry.lock scripts/ docs/test/module_1_test.md docs/superpowers/
git commit -m "feat(module-1): add Poetry setup and MQTT test scripts T3-T7"
```

Note: do NOT commit `.env` — it contains credentials. Verify `.gitignore` includes `.env` before committing.
