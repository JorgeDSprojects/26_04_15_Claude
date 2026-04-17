"""T2 — Verify simulator logs contain expected structlog events with correct fields.

structlog emits JSON lines. Checks:
- simulator.starting  → has fields: asset_path, interval_ms
- simulator.connected → has fields: host, port
- simulator.published → has fields: topic, val, ts  (at least one occurrence)

Run: python scripts/M2_Test/M2_T2.py"""
import json
import subprocess
import sys

failures: list[str] = []

result = subprocess.run(
    ["docker", "compose", "logs", "simulator", "--no-log-prefix"],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print(f"[FAIL] 'docker compose logs simulator' falló: {result.stderr.strip()}")
    sys.exit(1)

lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]

if not lines:
    print("[FAIL] T2 — No hay logs del simulator")
    sys.exit(1)

# Parse all JSON log lines; skip non-JSON (e.g. startup noise)
parsed: list[dict] = []
for line in lines:
    try:
        parsed.append(json.loads(line))
    except json.JSONDecodeError:
        pass

events_by_name: dict[str, list[dict]] = {}
for obj in parsed:
    name = obj.get("event", "")
    events_by_name.setdefault(name, []).append(obj)

# --- Check simulator.starting ---
starting = events_by_name.get("simulator.starting", [])
if not starting:
    failures.append("Evento 'simulator.starting' no encontrado")
    print("[FAIL] simulator.starting — no encontrado")
else:
    e = starting[0]
    ok = True
    for field in ("asset_path", "interval_ms"):
        if field not in e:
            failures.append(f"simulator.starting: falta campo '{field}'")
            ok = False
    if ok:
        print(f"[PASS] simulator.starting  asset_path={e['asset_path']}  interval_ms={e['interval_ms']}")
    else:
        print(f"[FAIL] simulator.starting — campos incompletos: {e}")

# --- Check simulator.connected ---
connected = events_by_name.get("simulator.connected", [])
if not connected:
    failures.append("Evento 'simulator.connected' no encontrado")
    print("[FAIL] simulator.connected — no encontrado")
else:
    e = connected[0]
    ok = True
    for field in ("host", "port"):
        if field not in e:
            failures.append(f"simulator.connected: falta campo '{field}'")
            ok = False
    if ok:
        print(f"[PASS] simulator.connected  host={e['host']}  port={e['port']}")
    else:
        print(f"[FAIL] simulator.connected — campos incompletos: {e}")

# --- Check simulator.published ---
published = events_by_name.get("simulator.published", [])
if not published:
    failures.append("Evento 'simulator.published' no encontrado")
    print("[FAIL] simulator.published — no encontrado")
else:
    pub_failures = []
    for e in published[:3]:  # check first 3
        for field in ("topic", "val", "ts"):
            if field not in e:
                pub_failures.append(f"falta campo '{field}' en: {e}")
    if pub_failures:
        for f in pub_failures:
            failures.append(f"simulator.published: {f}")
        print(f"[FAIL] simulator.published — campos incompletos")
    else:
        for e in published[:3]:
            print(f"[PASS] simulator.published  topic={e['topic']}  val={e['val']}  ts={e['ts']}")

if failures:
    print()
    for f in failures:
        print(f"[FAIL] {f}")
    print("\n[FAIL] T2 — logs del simulator incompletos o con formato incorrecto")
    sys.exit(1)
else:
    print("\n[PASS] T2 — structlog emite JSON con los 3 eventos y campos correctos")
    sys.exit(0)
