"""T1 — Verify that mqtt-broker and simulator containers are running.

Run: python scripts/M2_Test/M2_T1.py"""
import json
import subprocess
import sys

EXPECTED = {
    "aeronorth-mqtt-broker": {"up": True, "healthy": True},
    "aeronorth-simulator": {"up": True, "healthy": False},  # no healthcheck defined
}

failures: list[str] = []

result = subprocess.run(
    ["docker", "compose", "ps", "--format", "json"],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print(f"[FAIL] 'docker compose ps' falló: {result.stderr.strip()}")
    sys.exit(1)

# docker compose ps --format json outputs one JSON object per line
containers: dict[str, dict] = {}
for line in result.stdout.strip().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        name = obj.get("Name", "")
        containers[name] = obj
    except json.JSONDecodeError:
        pass

for name, reqs in EXPECTED.items():
    if name not in containers:
        failures.append(f"Container '{name}' no encontrado en 'docker compose ps'")
        continue
    obj = containers[name]
    state = (obj.get("State") or obj.get("Status") or "").lower()
    if "running" not in state and "up" not in state:
        failures.append(f"Container '{name}' no está corriendo (State='{state}')")
    if reqs["healthy"]:
        health = (obj.get("Health") or "").lower()
        if health != "healthy":
            failures.append(f"Container '{name}' no está healthy (Health='{health}')")

# Print results per container
for name, reqs in EXPECTED.items():
    if name in containers:
        obj = containers[name]
        state = obj.get("State") or obj.get("Status") or "?"
        health = obj.get("Health") or ""
        detail = f"State={state}" + (f", Health={health}" if health else "")
        ok = not any(name in f for f in failures)
        print(f"{'[PASS]' if ok else '[FAIL]'} {name}  ({detail})")
    else:
        print(f"[FAIL] {name}  (no encontrado)")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T1 — algún container no está listo")
    sys.exit(1)
else:
    print("\n[PASS] T1 — ambos containers Up, broker healthy")
    sys.exit(0)
