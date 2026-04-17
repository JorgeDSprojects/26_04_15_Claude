"""M4_T3 — Test full CRUD lifecycle for assets and signals.

Run from host (requires api-service running on localhost:8000):
    python scripts/M4_Test/M4_T3_crud_lifecycle.py

Creates a test asset + signal, updates them, then deletes them.
"""

import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {label}" + (f": {detail}" if detail else ""))
    if not condition:
        sys.exit(1)


def main() -> None:
    # Get a valid asset_type id
    _, asset_types = request("GET", "/api/v1/asset-types")
    enterprise_type = next((at for at in asset_types if at["name"] == "enterprise"), None)
    check("enterprise asset_type exists", enterprise_type is not None)

    # Get a valid signal_type id
    _, signal_types = request("GET", "/api/v1/signal-types")
    informative_type = next((st for st in signal_types if st["name"] == "informative"), None)
    check("informative signal_type exists", informative_type is not None)

    # Create test enterprise asset
    status, asset = request("POST", "/api/v1/assets", {
        "asset_type_id": enterprise_type["id"],
        "code": "test_crud_enterprise",
        "display_name": "Test CRUD Enterprise",
        "path": "test_crud_enterprise",
    })
    check("POST /api/v1/assets returns 201", status == 201, f"got {status}: {asset}")
    asset_id = asset["id"]
    check("created asset has correct path", asset["path"] == "test_crud_enterprise")

    # Create test signal
    status, signal = request("POST", "/api/v1/signals", {
        "asset_id": asset_id,
        "signal_type_id": informative_type["id"],
        "name": "test_val",
        "display_name": "Test Value",
        "unit": "unit",
        "datatype": "float",
        "criticality": "standard",
    })
    check("POST /api/v1/signals returns 201", status == 201, f"got {status}: {signal}")
    signal_id = signal["id"]
    expected_topic = "test_crud_enterprise/measure/test_val"
    check(
        "signal topic precomputed correctly",
        signal["topic"] == expected_topic,
        f"got '{signal['topic']}' expected '{expected_topic}'",
    )

    # PATCH signal criticality
    status, updated = request("PATCH", f"/api/v1/signals/{signal_id}", {"criticality": "buffered"})
    check("PATCH /api/v1/signals/{id} returns 200", status == 200, f"got {status}")
    check("criticality updated", updated["criticality"] == "buffered")

    # PATCH asset display_name
    status, updated_asset = request("PATCH", f"/api/v1/assets/{asset_id}", {"display_name": "Updated Name"})
    check("PATCH /api/v1/assets/{id} returns 200", status == 200, f"got {status}")
    check("display_name updated", updated_asset["display_name"] == "Updated Name")

    # GET signal by id
    status, fetched = request("GET", f"/api/v1/signals/{signal_id}")
    check("GET /api/v1/signals/{id} returns 200", status == 200)
    check("fetched signal matches", fetched["id"] == signal_id)

    # DELETE signal
    status, _ = request("DELETE", f"/api/v1/signals/{signal_id}")
    check("DELETE /api/v1/signals/{id} returns 204", status == 204, f"got {status}")

    # Verify signal is gone
    status, _ = request("GET", f"/api/v1/signals/{signal_id}")
    check("Signal 404 after delete", status == 404, f"got {status}")

    # DELETE asset
    status, _ = request("DELETE", f"/api/v1/assets/{asset_id}")
    check("DELETE /api/v1/assets/{id} returns 204", status == 204, f"got {status}")

    # Verify asset is gone
    status, _ = request("GET", f"/api/v1/assets/{asset_id}")
    check("Asset 404 after delete", status == 404, f"got {status}")

    print("\n[PASS] Full CRUD lifecycle verified.")


if __name__ == "__main__":
    main()
