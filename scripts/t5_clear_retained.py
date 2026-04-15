"""T5 — clears the retained message on demo/retained, then verifies nothing arrives.
Publishes an empty payload with retain=True (MQTT spec: empty retained = delete).
Expected output: [PASS] Retained message cleared."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
