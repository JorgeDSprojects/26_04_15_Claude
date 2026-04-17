"""T5 — Verify measure topics have no retained messages.

Steps:
1. Stop the simulator container
2. Connect a fresh subscriber and wait 5 s for any retained messages
3. Assert no messages received
4. Restart the simulator

Run: python scripts/M2_Test/M2_T5.py"""
import subprocess
import sys
import time

from mqtt_helper import connect

ASSET = "aeronorth/windfarm_north/sector_a/turbine_03"
TOPIC_FILTER = f"{ASSET}/+/measure/#"
WAIT_S = 5
RETRY_SECONDS = 5

failures: list[str] = []
retained_messages: list[tuple[str, str]] = []


def connect_with_retry():
    while True:
        try:
            return connect(client_id="m2-t5-retained-check")
        except ConnectionError as exc:
            print(f"[WARN] {exc} Reintentando en {RETRY_SECONDS}s... (Ctrl+C para parar)")
            time.sleep(RETRY_SECONDS)


# Step 1: Stop simulator
print("Parando el simulator...")
r = subprocess.run(["docker", "compose", "stop", "simulator"], capture_output=True, text=True)
if r.returncode != 0:
    print(f"[FAIL] No se pudo parar el simulator: {r.stderr.strip()}")
    sys.exit(1)
print("[PASS] Simulator parado")
time.sleep(2)  # brief pause so broker processes the disconnect

# Step 2: Connect fresh subscriber and collect any retained messages
print(f"\nConectando suscriptor fresco y esperando {WAIT_S}s para mensajes retained...")

def on_message(c, userdata, msg):
    retained_messages.append((msg.topic, msg.payload.decode("utf-8", errors="replace")))

client = connect_with_retry()
client.on_message = on_message
client.subscribe(TOPIC_FILTER, qos=0)
time.sleep(WAIT_S)
client.loop_stop()
client.disconnect()

# Step 3: Assert no retained messages
if retained_messages:
    for topic, payload in retained_messages:
        failures.append(f"Mensaje retained recibido en {topic}: {payload[:80]}")
    print(f"[FAIL] Se recibieron {len(retained_messages)} mensaje(s) retained")
else:
    print("[PASS] Ningún mensaje retained recibido")

# Step 4: Restart simulator regardless of test result
print("\nReiniciando el simulator...")
r = subprocess.run(["docker", "compose", "start", "simulator"], capture_output=True, text=True)
if r.returncode != 0:
    print(f"[WARN] No se pudo reiniciar el simulator: {r.stderr.strip()}")
else:
    print("[PASS] Simulator reiniciado")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T5 — los topics de measure tienen mensajes retained (retain=True no permitido)")
    sys.exit(1)
else:
    print("\n[PASS] T5 — sin mensajes retained en topics de measure")
    sys.exit(0)
