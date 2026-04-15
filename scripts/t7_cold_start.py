"""T7 cold start — verifies that retained messages survive a container restart.
Must be run from the project root (where docker-compose.yml lives).
Flow: publish retained → restart mqtt-broker → wait for healthy → verify retained arrives."""
import subprocess
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import publish, subscribe


def wait_for_healthy(timeout: int = 60) -> bool:
    """Poll docker compose ps until mqtt-broker shows (healthy). Returns True if healthy within timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "compose", "ps", "mqtt-broker"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
subprocess.run(
    ["docker", "compose", "restart", "mqtt-broker"],
    check=True,
    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
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
