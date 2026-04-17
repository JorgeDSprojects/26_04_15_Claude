"""T6 — Verify the simulator interval is configurable via SIM_INTERVAL_MS.

Steps:
1. Restart simulator with SIM_INTERVAL_MS=3000
2. Subscribe and measure time between consecutive messages on the same topic
3. Verify interval is < 5 s (not the default 10 s)
4. Restore simulator to default interval

Run: python scripts/M2_Test/M2_T6.py"""
import json
import os
import subprocess
import sys
import time

from mqtt_helper import connect

ASSET = "aeronorth/windfarm_north/sector_a/turbine_03"
RPM_TOPIC = f"{ASSET}/rotor/measure/rpm"
TOPIC_FILTER = f"{ASSET}/+/measure/#"
OVERRIDE_INTERVAL_MS = 3000
MAX_EXPECTED_INTERVAL_S = 5.0
COLLECT_S = 20
RETRY_SECONDS = 5
STARTUP_WAIT_S = 8  # time to let the simulator connect after restart

failures: list[str] = []
message_times: list[float] = []


def connect_with_retry():
    while True:
        try:
            return connect()
        except ConnectionError as exc:
            print(f"[WARN] {exc} Reintentando en {RETRY_SECONDS}s... (Ctrl+C para parar)")
            time.sleep(RETRY_SECONDS)


def on_message(c, userdata, msg):
    if msg.topic == RPM_TOPIC:
        message_times.append(time.time())
        try:
            data = json.loads(msg.payload.decode())
            print(f"  rpm={data.get('val')}  ts={data.get('ts')}")
        except (json.JSONDecodeError, KeyError):
            pass


# Step 1: Restart simulator with overridden interval
env = {**os.environ, "SIM_INTERVAL_MS": str(OVERRIDE_INTERVAL_MS)}
print(f"Reiniciando simulator con SIM_INTERVAL_MS={OVERRIDE_INTERVAL_MS}...")
r = subprocess.run(
    ["docker", "compose", "up", "-d", "simulator"],
    capture_output=True, text=True, env=env,
)
if r.returncode != 0:
    print(f"[FAIL] No se pudo reiniciar el simulator: {r.stderr.strip()}")
    sys.exit(1)
print(f"[PASS] Simulator reiniciado. Esperando {STARTUP_WAIT_S}s para que conecte...")
time.sleep(STARTUP_WAIT_S)

# Step 2: Collect messages and measure intervals
print(f"\nRecolectando mensajes de rpm durante {COLLECT_S}s...\n")
client = connect_with_retry()
client.on_message = on_message
client.subscribe(RPM_TOPIC, qos=0)
time.sleep(COLLECT_S)
client.loop_stop()
client.disconnect()

print()

# Step 3: Calculate intervals
if len(message_times) < 2:
    failures.append(f"Solo se recibieron {len(message_times)} mensaje(s) de rpm — no suficiente para medir intervalo")
else:
    intervals = [message_times[i+1] - message_times[i] for i in range(len(message_times)-1)]
    avg_interval = sum(intervals) / len(intervals)
    max_interval = max(intervals)
    print(f"  Mensajes recibidos : {len(message_times)}")
    print(f"  Intervalo promedio : {avg_interval:.2f}s")
    print(f"  Intervalo máximo   : {max_interval:.2f}s")
    if avg_interval > MAX_EXPECTED_INTERVAL_S:
        failures.append(
            f"Intervalo promedio {avg_interval:.2f}s > {MAX_EXPECTED_INTERVAL_S}s "
            f"— SIM_INTERVAL_MS={OVERRIDE_INTERVAL_MS} no tuvo efecto"
        )
    else:
        print(f"[PASS] Intervalo ~{avg_interval:.1f}s (esperado < {MAX_EXPECTED_INTERVAL_S}s)")

# Step 4: Restore default interval
print("\nRestaurando simulator con intervalo por defecto (10000ms)...")
r = subprocess.run(
    ["docker", "compose", "up", "-d", "simulator"],
    capture_output=True, text=True,
)
if r.returncode != 0:
    print(f"[WARN] No se pudo restaurar el simulator: {r.stderr.strip()}")
else:
    print("[PASS] Simulator restaurado al intervalo por defecto")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T6 — intervalo configurable no funciona")
    sys.exit(1)
else:
    print("\n[PASS] T6 — SIM_INTERVAL_MS funciona correctamente")
    sys.exit(0)
