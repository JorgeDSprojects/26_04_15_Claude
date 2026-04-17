"""M4_T1 — Seed the ISA-95 asset hierarchy and create the rpm signal.

Run from host (requires api-service running on localhost:8000):
    python scripts/M4_Test/M4_T1_seed_assets.py

Expected output: prints each created asset/signal with its id and (for signals) its topic.
"""

import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get(path: str) -> list | dict:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read())


def main() -> None:
    # Verify API is up
    try:
        health = get("/health")
        assert health["status"] == "ok", f"Unexpected health: {health}"
        print(f"[OK] Health: {health}")
    except Exception as exc:
        print(f"[FAIL] Cannot reach API at {BASE}: {exc}")
        sys.exit(1)

    # Get asset type IDs by name
    asset_types = {at["name"]: at["id"] for at in get("/api/v1/asset-types")}
    signal_types = {st["name"]: st["id"] for st in get("/api/v1/signal-types")}
    print(f"[OK] Asset types: {list(asset_types.keys())}")
    print(f"[OK] Signal types: {list(signal_types.keys())}")

    # Create asset hierarchy
    hierarchy = [
        (None, "enterprise", "aeronorth", "AeroNorth", "aeronorth"),
        (None, "wind_farm", "windfarm_north", "Wind Farm North", "aeronorth/windfarm_north"),
        (None, "sector", "sector_a", "Sector A", "aeronorth/windfarm_north/sector_a"),
        (None, "wind_turbine", "turbine_03", "Turbine 03", "aeronorth/windfarm_north/sector_a/turbine_03"),
        (None, "rotor", "rotor", "Turbine 03 > Rotor", "aeronorth/windfarm_north/sector_a/turbine_03/rotor"),
        (None, "nacelle", "nacelle", "Turbine 03 > Nacelle", "aeronorth/windfarm_north/sector_a/turbine_03/nacelle"),
        (None, "generator", "generator", "Turbine 03 > Generator", "aeronorth/windfarm_north/sector_a/turbine_03/generator"),
    ]

    created_ids: dict[str, int] = {}
    parent_map = {
        "aeronorth": None,
        "windfarm_north": "aeronorth",
        "sector_a": "windfarm_north",
        "turbine_03": "sector_a",
        "rotor": "turbine_03",
        "nacelle": "turbine_03",
        "generator": "turbine_03",
    }

    for _, type_name, code, display, path in hierarchy:
        parent_code = parent_map[code]
        parent_id = created_ids.get(parent_code) if parent_code else None
        try:
            asset = post(
                "/api/v1/assets",
                {
                    "parent_id": parent_id,
                    "asset_type_id": asset_types[type_name],
                    "code": code,
                    "display_name": display,
                    "path": path,
                },
            )
            created_ids[code] = asset["id"]
            print(f"[OK] Asset created: id={asset['id']} path={asset['path']}")
        except Exception as exc:
            print(f"[WARN] Asset {code} may already exist: {exc}")

    # Create signals
    signals_to_create = [
        {
            "asset_code": "rotor",
            "name": "rpm",
            "display_name": "Rotor RPM",
            "unit": "rpm",
            "datatype": "float",
            "criticality": "buffered",
            "signal_type": "informative",
            "min_value": 0,
            "max_value": 25,
            "expected_topic": "aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm",
        },
        {
            "asset_code": "nacelle",
            "name": "wind_speed",
            "display_name": "Wind Speed",
            "unit": "m/s",
            "datatype": "float",
            "criticality": "standard",
            "signal_type": "informative",
            "min_value": 0,
            "max_value": 50,
            "expected_topic": "aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed",
        },
        {
            "asset_code": "generator",
            "name": "active_power",
            "display_name": "Active Power",
            "unit": "kW",
            "datatype": "float",
            "criticality": "standard",
            "signal_type": "informative",
            "min_value": 0,
            "max_value": 2000,
            "expected_topic": "aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power",
        },
    ]

    all_assets = {a["path"].split("/")[-1]: a["id"] for a in get("/api/v1/assets")}

    for sig in signals_to_create:
        asset_id = all_assets.get(sig["asset_code"])
        if not asset_id:
            print(f"[WARN] Asset '{sig['asset_code']}' not found, skipping signal {sig['name']}")
            continue
        try:
            created = post(
                "/api/v1/signals",
                {
                    "asset_id": asset_id,
                    "signal_type_id": signal_types[sig["signal_type"]],
                    "name": sig["name"],
                    "display_name": sig["display_name"],
                    "unit": sig["unit"],
                    "datatype": sig["datatype"],
                    "criticality": sig["criticality"],
                    "min_value": sig["min_value"],
                    "max_value": sig["max_value"],
                },
            )
            topic_ok = created["topic"] == sig["expected_topic"]
            status = "[OK]" if topic_ok else "[FAIL]"
            print(f"{status} Signal '{sig['name']}' topic={created['topic']}")
            if not topic_ok:
                print(f"       Expected: {sig['expected_topic']}")
        except Exception as exc:
            print(f"[WARN] Signal {sig['name']} may already exist or failed: {exc}")

    print("\n--- Final signal list ---")
    for s in get("/api/v1/signals"):
        print(f"  id={s['id']:3d}  criticality={s['criticality']:10s}  topic={s['topic']}")


if __name__ == "__main__":
    main()
