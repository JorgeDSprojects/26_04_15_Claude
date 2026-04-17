"""T4 — Verify rpm values oscillate (sine wave, not constant).

Collects rpm samples for ~70 seconds and checks that min != max.
Expected range: 0–20 RPM with a 60 s period.

Run: python scripts/M2_Test/M2_T4.py"""
import json
import sys
import time

from mqtt_helper import connect

ASSET = "aeronorth/windfarm_north/sector_a/turbine_03"
RPM_TOPIC = f"{ASSET}/rotor/measure/rpm"
SAMPLE_DURATION_S = 70
RETRY_SECONDS = 5

rpm_values: list[float] = []
failures: list[str] = []


def connect_with_retry():
    while True:
        try:
            return connect()
        except ConnectionError as exc:
            print(f"[WARN] {exc} Reintentando en {RETRY_SECONDS}s... (Ctrl+C para parar)")
            time.sleep(RETRY_SECONDS)


def on_message(c, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        val = float(data["val"])
        rpm_values.append(val)
        print(f"  rpm={val}")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        failures.append(f"Payload inválido: {exc}")


client = connect_with_retry()
client.on_message = on_message
client.subscribe(RPM_TOPIC, qos=0)

print(f"Recolectando muestras de rpm durante {SAMPLE_DURATION_S}s...")
print(f"Topic: {RPM_TOPIC}\n")

try:
    time.sleep(SAMPLE_DURATION_S)
except KeyboardInterrupt:
    print("\nInterrumpido por el usuario.")
finally:
    client.loop_stop()
    client.disconnect()

print()

if not rpm_values:
    print("[FAIL] No se recibió ningún mensaje de rpm")
    sys.exit(1)

min_val = min(rpm_values)
max_val = max(rpm_values)
spread = max_val - min_val

print(f"  Muestras recibidas : {len(rpm_values)}")
print(f"  Mín: {min_val:.2f}  Máx: {max_val:.2f}  Rango: {spread:.2f}")

if spread < 0.01:
    failures.append(f"Los valores de rpm no cambian (spread={spread:.4f}) — sine wave no funciona")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T4 — rpm parece constante")
    sys.exit(1)
else:
    print("\n[PASS] T4 — rpm oscila correctamente (sine wave activa)")
    sys.exit(0)
