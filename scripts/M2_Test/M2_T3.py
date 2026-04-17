"""T3 HITO — Subscribe to turbine_03 measure topics and verify 3 cycles.

Checks:
- All 3 expected topics appear
- Each payload has keys: val, ts (13 digits), q == 1
- Messages repeat for at least 3 complete cycles (~30 s)

Run: python scripts/M2_Test/M2_T3.py
Stop with Ctrl+C (script exits automatically after 3 cycles pass or timeout)."""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime

from mqtt_helper import connect

ASSET = "aeronorth/windfarm_north/sector_a/turbine_03"
TOPIC_FILTER = f"{ASSET}/+/measure/#"
EXPECTED_TOPICS = {
    f"{ASSET}/rotor/measure/rpm",
    f"{ASSET}/nacelle/measure/wind_speed",
    f"{ASSET}/generator/measure/active_power",
}
QOS = 0
REQUIRED_CYCLES = 3
TIMEOUT_S = 120  # 3 cycles × 10 s + margin
RETRY_SECONDS = 5

failures: list[str] = []
topic_counts: dict[str, int] = defaultdict(int)


def _validate_payload(topic: str, raw: str) -> bool:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        failures.append(f"Payload no es JSON válido en {topic}: {exc}")
        return False
    ok = True
    if "val" not in data:
        failures.append(f"{topic}: falta clave 'val'")
        ok = False
    if "ts" not in data:
        failures.append(f"{topic}: falta clave 'ts'")
        ok = False
    elif len(str(int(data["ts"]))) != 13:
        failures.append(f"{topic}: 'ts' no tiene 13 dígitos (val={data['ts']})")
        ok = False
    if data.get("q") != 1:
        failures.append(f"{topic}: 'q' != 1 (val={data.get('q')})")
        ok = False
    return ok


def connect_with_retry():
    while True:
        try:
            return connect()
        except ConnectionError as exc:
            print(f"[WARN] {exc} Reintentando en {RETRY_SECONDS}s... (Ctrl+C para parar)")
            time.sleep(RETRY_SECONDS)


def on_message(c, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="replace")
    ts_str = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts_str}] {topic}  {raw}")
    _validate_payload(topic, raw)
    topic_counts[topic] += 1


client = connect_with_retry()
client.on_message = on_message
client.subscribe(TOPIC_FILTER, qos=QOS)

print(f"Suscrito a: {TOPIC_FILTER}")
print(f"Esperando {REQUIRED_CYCLES} ciclos completos (timeout {TIMEOUT_S}s)...\n")

deadline = time.time() + TIMEOUT_S
try:
    while time.time() < deadline:
        min_cycles = min((topic_counts[t] for t in EXPECTED_TOPICS), default=0)
        if min_cycles >= REQUIRED_CYCLES:
            break
        time.sleep(1)
except KeyboardInterrupt:
    print("\nInterrumpido por el usuario.")
finally:
    client.loop_stop()
    client.disconnect()

print()

# --- Evaluación final ---
# 1. Todos los topics esperados recibidos
for t in EXPECTED_TOPICS:
    if topic_counts[t] == 0:
        failures.append(f"Topic nunca recibido: {t}")

# 2. Al menos 3 ciclos en cada topic
for t in EXPECTED_TOPICS:
    if 0 < topic_counts[t] < REQUIRED_CYCLES:
        failures.append(f"{t}: solo {topic_counts[t]} mensaje(s), se requieren {REQUIRED_CYCLES}")

# Resumen
passed = len(failures) == 0
for t in sorted(EXPECTED_TOPICS):
    cycles = topic_counts[t]
    status = "[PASS]" if cycles >= REQUIRED_CYCLES else "[FAIL]"
    print(f"{status} {t}  ({cycles} mensajes)")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T3 HITO — validación fallida")
    sys.exit(1)
else:
    print("\n[PASS] T3 HITO — 3 topics, payload válido, 3+ ciclos completados")
    sys.exit(0)
