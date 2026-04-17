"""T7 — Verify docker compose config is valid and contains expected services.

Checks:
- 'docker compose config' exits with code 0
- Output contains 'mqtt-broker' service
- Output contains 'simulator' service
- Output contains 'depends_on' (simulator depends on mqtt-broker)

Run: python scripts/M2_Test/M2_T7.py"""
import subprocess
import sys

failures: list[str] = []

result = subprocess.run(
    ["docker", "compose", "config"],
    capture_output=True,
    text=True,
)

# Check 1: exit code
if result.returncode != 0:
    print(f"[FAIL] 'docker compose config' terminó con error:\n{result.stderr.strip()}")
    sys.exit(1)
print("[PASS] 'docker compose config' sin errores (returncode=0)")

output = result.stdout

# Check 2: mqtt-broker present
if "mqtt-broker" in output:
    print("[PASS] Servicio 'mqtt-broker' presente en la config")
else:
    failures.append("Servicio 'mqtt-broker' no encontrado en la config")
    print("[FAIL] Servicio 'mqtt-broker' no encontrado")

# Check 3: simulator present
if "simulator" in output:
    print("[PASS] Servicio 'simulator' presente en la config")
else:
    failures.append("Servicio 'simulator' no encontrado en la config")
    print("[FAIL] Servicio 'simulator' no encontrado")

# Check 4: depends_on present
if "depends_on" in output:
    print("[PASS] 'depends_on' presente en la config")
else:
    failures.append("'depends_on' no encontrado — simulator debería depender de mqtt-broker")
    print("[FAIL] 'depends_on' no encontrado")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T7 — docker compose config inválida o incompleta")
    sys.exit(1)
else:
    print("\n[PASS] T7 — docker compose config válida con ambos servicios y depends_on")
    sys.exit(0)
