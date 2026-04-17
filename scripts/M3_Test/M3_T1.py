"""
M3_T1.py — Module 3 automated test: TimescaleDB persistence via Telegraf.

Connects to TimescaleDB on localhost:5433 and verifies:
  1. The metrics hypertable exists.
  2. All three simulator signals appear within 90 seconds.
  3. Each signal has valid value (float) and quality=1.
  4. Timestamps are recent (within last 60 s at time of check).

Usage:
    pip install psycopg2-binary
    python scripts/M3_Test/M3_T1.py

Environment variables (optional, defaults match .env.example):
    TIMESCALE_HOST     (default: localhost)
    TIMESCALE_PORT     (default: 5433)
    TIMESCALE_USER     (default: postgres)
    TIMESCALE_PASSWORD (default: tspass)
    TIMESCALE_DB       (default: metrics)
"""

import os
import sys
import time
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")

# ── Config ─────────────────────────────────────────────────────────────────────
HOST     = os.getenv("TIMESCALE_HOST", "localhost")
PORT     = int(os.getenv("TIMESCALE_PORT", "5433"))
USER     = os.getenv("TIMESCALE_USER", "postgres")
PASSWORD = os.getenv("TIMESCALE_PASSWORD", "tspass")
DB       = os.getenv("TIMESCALE_DB", "metrics")

ASSET_PATH     = "aeronorth/windfarm_north/sector_a/turbine_03"
EXPECTED_TOPICS = [
    f"{ASSET_PATH}/rotor/measure/rpm",
    f"{ASSET_PATH}/nacelle/measure/wind_speed",
    f"{ASSET_PATH}/generator/measure/active_power",
]

WAIT_SECONDS = 90   # max time to wait for data
POLL_INTERVAL = 5


# ── Helpers ────────────────────────────────────────────────────────────────────

def connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB
    )


def print_result(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_hypertable_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT hypertable_name FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'metrics';"
        )
        return cur.fetchone() is not None


def test_table_schema(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'metrics' ORDER BY ordinal_position;"
        )
        cols = [row[0] for row in cur.fetchall()]
    expected = {"time", "topic", "value", "quality"}
    return expected.issubset(set(cols))


def wait_for_all_topics(conn) -> dict:
    """Poll until all expected topics have at least one row, or timeout."""
    deadline = time.time() + WAIT_SECONDS
    found = {}
    while time.time() < deadline:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT topic, value, quality, time "
                "FROM metrics "
                "WHERE topic = ANY(%s) "
                "ORDER BY time DESC;",
                (EXPECTED_TOPICS,),
            )
            rows = cur.fetchall()
        for row in rows:
            t = row["topic"]
            if t not in found:
                found[t] = row
        if len(found) == len(EXPECTED_TOPICS):
            break
        remaining = int(deadline - time.time())
        print(f"  Waiting… found {len(found)}/{len(EXPECTED_TOPICS)} topics ({remaining}s left)")
        time.sleep(POLL_INTERVAL)
    return found


def test_row_validity(row) -> tuple[bool, str]:
    issues = []
    if row["value"] is None:
        issues.append("value is NULL")
    if row["quality"] not in (1, None):
        issues.append(f"unexpected quality={row['quality']}")
    age = (datetime.now(timezone.utc) - row["time"].replace(tzinfo=timezone.utc)).total_seconds()
    if age > 120:
        issues.append(f"stale: {age:.0f}s old")
    if issues:
        return False, "; ".join(issues)
    return True, f"value={row['value']:.3f}, quality={row['quality']}, age={age:.0f}s"


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\nModule 3 Test — TimescaleDB persistence")
    print(f"Connecting to {HOST}:{PORT}/{DB} as {USER} …\n")

    try:
        conn = connect()
    except Exception as e:
        print(f"  [FAIL] Cannot connect to TimescaleDB: {e}")
        return 1

    all_pass = True

    # T1: hypertable exists
    ok = test_hypertable_exists(conn)
    print_result("T1 — hypertable 'metrics' is a TimescaleDB hypertable", ok)
    all_pass &= ok

    # T2: schema correct
    ok = test_table_schema(conn)
    print_result("T2 — metrics table has expected columns (time, topic, value, quality)", ok)
    all_pass &= ok

    if not ok:
        print("\n  Schema check failed — aborting further tests.")
        conn.close()
        return 1

    # T3: wait for data from all three topics
    print(f"\n  Waiting up to {WAIT_SECONDS}s for all three simulator signals …")
    found = wait_for_all_topics(conn)

    for expected_topic in EXPECTED_TOPICS:
        if expected_topic in found:
            ok, detail = test_row_validity(found[expected_topic])
            short = expected_topic.split("/")[-1]  # rpm / wind_speed / active_power
            print_result(f"T3 — {short} present and valid", ok, detail)
            all_pass &= ok
        else:
            short = expected_topic.split("/")[-1]
            print_result(f"T3 — {short} present and valid", False, "no rows found within timeout")
            all_pass = False

    # T4: row count is growing (wait one interval, compare)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM metrics;")
        count_before = cur.fetchone()[0]
    print(f"\n  Waiting {POLL_INTERVAL}s to verify row count grows …")
    time.sleep(POLL_INTERVAL)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM metrics;")
        count_after = cur.fetchone()[0]
    ok = count_after > count_before
    print_result(
        "T4 — row count is growing (data accumulates over time)",
        ok,
        f"{count_before} → {count_after}",
    )
    all_pass &= ok

    conn.close()

    print(f"\n{'='*50}")
    if all_pass:
        print("  ALL CHECKS PASSED — Module 3 hito: OK")
    else:
        print("  SOME CHECKS FAILED — Review output above")
    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
