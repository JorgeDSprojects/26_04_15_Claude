"""M4_T2 — Verify that all signals have correct precomputed topics.

Run from host (requires api-service running on localhost:8000):
    python scripts/M4_Test/M4_T2_verify_topics.py

Checks that:
1. All signal topics follow the pattern <asset_path>/<namespace>/<signal_name>
2. Namespace segments are correct per signal type
3. No client-supplied topics were accepted (they are all server-computed)
"""

import json
import sys
import urllib.request

BASE = "http://localhost:8000"

NAMESPACE_MAP = {
    "informative": "measure",
    "operational": "events",
    "descriptive": "$meta",
    "analytic": "$analytics",
}


def get(path: str) -> list | dict:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read())


def main() -> None:
    signals = get("/api/v1/signals")
    assets = {a["id"]: a for a in get("/api/v1/assets")}
    signal_types = {st["id"]: st for st in get("/api/v1/signal-types")}

    if not signals:
        print("[WARN] No signals found. Run M4_T1_seed_assets.py first.")
        sys.exit(1)

    failures = 0
    for sig in signals:
        asset = assets.get(sig["asset_id"])
        stype = signal_types.get(sig["signal_type_id"])
        if not asset or not stype:
            print(f"[FAIL] Signal id={sig['id']} references unknown asset or signal_type")
            failures += 1
            continue

        namespace = NAMESPACE_MAP.get(stype["name"])
        expected_topic = f"{asset['path']}/{namespace}/{sig['name']}"

        if sig["topic"] == expected_topic:
            print(f"[OK] id={sig['id']:3d}  topic={sig['topic']}")
        else:
            print(f"[FAIL] id={sig['id']:3d}  got={sig['topic']}")
            print(f"               expected={expected_topic}")
            failures += 1

    print(f"\nResult: {len(signals) - failures}/{len(signals)} signals pass topic validation")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
