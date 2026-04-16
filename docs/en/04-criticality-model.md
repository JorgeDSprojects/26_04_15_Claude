# 04 — Criticality Model

## Purpose

Each signal in the registry has a `criticality` attribute that
determines how the system handles message buffering, delivery
guarantees, and client reconnection behavior. The criticality is
configured per signal from the admin UI and stored in the `signals`
table.

## The three levels

### `standard` — best effort, low overhead

**Behavior:**
- MQTT QoS: 0 (fire and forget)
- `realtime-service` buffer: in-memory asyncio.Queue per client, fixed
  size (default 100 messages), drop-oldest on overflow.
- Redis: LKV written (for initial load on new widgets), NO stream.
- On client reconnect: client gets the LKV immediately, then resumes
  from the live stream. Messages missed during disconnection are lost.

**Use case:** Signals where the latest value is what matters, and
missing a few samples between disconnections is acceptable. Ambient
temperature, yaw angle, wind direction, tower acceleration.

**Why not always use buffered?** Because it wastes Redis memory and adds
write latency for signals that don't need it. In a system with 10,000
signals, the difference between writing every message to a Redis Stream
vs. just keeping the last value matters.

### `buffered` — continuity with catch-up

**Behavior:**
- MQTT QoS: 0 (no broker-level guarantee — the buffer is at the
  application layer, not the transport layer).
- `realtime-service` buffer: Redis Stream per topic.
  - On every MQTT message received, `realtime-service` does `XADD`
    to `stream:<topic>` with `MAXLEN ~ 1000` (approximate trimming).
  - Each WebSocket client has a tracked last-read stream ID stored in
    `ws:session:<client_id>` hash.
  - On reconnect, `realtime-service` does `XREAD` from the client's
    last ID, sends the gap, then resumes live.
- Redis LKV: also written (same as standard).
- Stream retention: ~1000 messages per topic (configurable). At 10s
  intervals, that's ~2.7 hours of buffer. Enough for typical
  disconnections.

**Use case:** Signals where continuity matters for charts and trends.
Wind speed, active power, RPM, bearing temperatures, oil pressure,
vibration.

**Why not QoS 1?** Because the QoS guarantee is between broker and
`realtime-service`, not between `realtime-service` and the browser. The
browser doesn't speak MQTT. So QoS 1 at the broker level doesn't help
for the WebSocket segment. The Redis Stream handles that segment.

### `critical` — guaranteed delivery for events

**Behavior:**
- MQTT QoS: 1 (at-least-once delivery between broker and all
  subscribers, including `realtime-service` and `event-ingestor`).
- `realtime-service` buffer: Redis Stream (same as buffered, but with
  larger `MAXLEN ~ 10000`).
- `event-ingestor`: subscribes with QoS 1 AND persistent session.
  If the ingestor is down, the broker queues messages until it comes
  back.
- Redis LKV: written.

**Use case:** Operational events and alarms where losing a single
message is unacceptable. Emergency stops, grid loss, overtemperature
alarms, operational state transitions.

**Why not QoS 2?** QoS 2 (exactly-once) adds significant latency and
complexity. QoS 1 (at-least-once) with idempotent consumers (check
`occurred_at` + `event_type` + `asset_id` for dedup) is the industry
standard for industrial IoT.

## Summary table

| Aspect                     | `standard`      | `buffered`        | `critical`        |
|----------------------------|-----------------|-------------------|-------------------|
| MQTT QoS                   | 0               | 0                 | 1                 |
| WS buffer type             | In-memory queue | Redis Stream      | Redis Stream      |
| WS buffer size             | 100 messages    | ~1000 messages    | ~10000 messages   |
| Reconnect behavior         | LKV only        | LKV + catch-up    | LKV + catch-up    |
| Messages lost on WS drop   | Yes             | No (within buffer)| No (within buffer)|
| Broker queues if sub down  | No              | No                | Yes               |
| Redis write per message    | SET (LKV only)  | SET + XADD        | SET + XADD        |
| Typical signals            | Ambient temp    | Wind speed, power | Alarms, states    |

## Configuration in the UI

The admin interface exposes criticality as a dropdown on the signal
edit form with three options: Standard, Buffered, Critical. Changing
criticality triggers:

1. `api-service` updates the `signals` table.
2. Postgres NOTIFY fires.
3. `sync-service` republishes the `$meta` retained message with the
   updated criticality.
4. `realtime-service` (which caches signal metadata in memory) receives
   the updated `$meta` from the broker and adjusts its buffering
   strategy for that topic.

**No restart required.** The change propagates automatically.

## Implementation notes for `realtime-service`

```python
# Pseudocode for message handling based on criticality

async def handle_mqtt_message(topic: str, payload: bytes):
    signal_meta = signal_cache.get(topic)
    criticality = signal_meta.criticality if signal_meta else "standard"

    # Always update LKV
    await redis.set(f"lkv:{topic}", payload)

    if criticality in ("buffered", "critical"):
        maxlen = 10000 if criticality == "critical" else 1000
        await redis.xadd(f"stream:{topic}", {"payload": payload}, maxlen=maxlen)

    # Fan-out to connected WebSocket clients
    for client in get_subscribers(topic):
        if criticality == "standard":
            client.memory_queue.put_nowait_or_drop(payload)
        else:
            # Client reads from Redis Stream, not memory queue
            await notify_client_new_data(client, topic)
```

## Adding a fourth level

**Do not add a fourth criticality level without discussing with the
project owner.** The three levels cover the known use cases. Adding
levels increases complexity in `realtime-service`, Redis resource usage,
and UI cognitive load. If a new use case arises, document it and discuss
whether it truly needs a new level or can be served by adjusting the
parameters of an existing one.
