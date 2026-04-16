# 03 — MQTT Topic Structure and Payloads

## Topic hierarchy

All topics follow ISA-95 levels, separated by `/`:

```
<enterprise>/<site>/<area>/<line>/<cell>/<namespace>/<signal_name>
```

### Namespace segments

| Namespace     | Purpose                    | MQTT flag    | QoS default | Example suffix              |
|---------------|----------------------------|-------------|-------------|------------------------------|
| `measure`     | Real-time telemetry        | no retain   | 0 or 1*     | `.../measure/rpm`            |
| `$meta`       | Descriptive metadata       | retain=true | 1           | `.../$meta/rpm`              |
| `events`      | Operational events/alarms  | no retain   | 1           | `.../events/emergency_stop`  |
| `$analytics`  | Computed KPIs/predictions  | no retain   | 0           | `.../$analytics/efficiency`  |

*QoS for `measure` depends on signal criticality: `standard` → QoS 0,
`buffered` → QoS 0, `critical` → QoS 1.

### Wind farm example topics

```
# Enterprise level
aeronorth/

# Site
aeronorth/windfarm_north/

# Area
aeronorth/windfarm_north/sector_a/

# Line (turbine)
aeronorth/windfarm_north/sector_a/turbine_03/

# Cell (component) + namespace + signal
aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/temperature_winding_u
aeronorth/windfarm_north/sector_a/turbine_03/gearbox/measure/oil_temperature
aeronorth/windfarm_north/sector_a/turbine_03/controller/events/emergency_stop
aeronorth/windfarm_north/sector_a/turbine_03/controller/events/high_wind_cutoff
aeronorth/windfarm_north/sector_a/turbine_03/rotor/$meta/rpm
aeronorth/windfarm_north/sector_a/turbine_03/controller/$analytics/total_energy_produced
```

### Wildcard subscription patterns

| Consumer         | Pattern                                    | Purpose                         |
|------------------|--------------------------------------------|---------------------------------|
| Telegraf         | `+/+/+/+/+/measure/#`                     | All informative telemetry       |
| event-ingestor   | `+/+/+/+/+/events/#`                      | All operational events          |
| meta-ingestor    | `+/+/+/+/+/$meta/#`                       | All descriptive metadata        |
| realtime-service | Dynamic, per client subscription            | Only topics the client wants    |

## Payload formats

### Informative (`measure`) — optimized

```json
{
    "val": 145.6,
    "ts": 1705400100500,
    "q": 1
}
```

| Field | Type   | Description                              |
|-------|--------|------------------------------------------|
| `val` | number | Signal value                             |
| `ts`  | int    | Unix timestamp in milliseconds (epoch)   |
| `q`   | int    | Quality: 1 = good, 0 = bad/stale        |

**Why optimized?** The topic already carries the context (which asset,
which signal). The payload only carries what changes: value, time,
quality. This follows the UNS principle of Lightweight messages. Unit,
description, and other metadata live in `$meta`, not here.

### Informative — dataset (grouped signals)

When multiple signals from the same component change simultaneously,
a single grouped message saves overhead:

```json
{
    "ts": 1705400100500,
    "q": 1,
    "d": {
        "temperature_winding_u": 85.2,
        "temperature_winding_v": 83.1,
        "temperature_winding_w": 84.7
    }
}
```

Topic: `.../generator/measure/dataset`

This is optional. Individual topics per signal is the default.

### Descriptive (`$meta`) — full metadata

Published by `sync-service` with `retain=true`.

```json
{
    "signal_id": 42,
    "name": "rpm",
    "display_name": "Rotor RPM",
    "unit": "rpm",
    "datatype": "float",
    "criticality": "buffered",
    "min_value": 0,
    "max_value": 25,
    "enabled": true,
    "asset_path": "aeronorth/windfarm_north/sector_a/turbine_03/rotor",
    "asset_display_name": "Turbine 03 > Rotor",
    "updated_at": "2024-01-16T10:00:00Z"
}
```

### Operational (`events`) — event payload

Published by producers (simulator, gateways) with QoS 1.

```json
{
    "event_type": "emergency_stop",
    "severity": "critical",
    "ts": 1705400100500,
    "data": {
        "trigger": "manual",
        "wind_speed_at_trigger": 28.3,
        "rotor_rpm_at_trigger": 0
    }
}
```

| Field        | Type   | Description                              |
|--------------|--------|------------------------------------------|
| `event_type` | string | Matches `events.event_type` in Postgres  |
| `severity`   | string | One of: info, warning, error, critical   |
| `ts`         | int    | When the event occurred (epoch ms)       |
| `data`       | object | Event-specific context, free-form JSON   |

### Analytic (`$analytics`) — computed values

Published by analytics services (future) or the simulator for demo.

```json
{
    "val": 0.85,
    "ts": 1705400100500,
    "window": "1h",
    "model": "linear_regression_v1"
}
```

## Topic computation from registry

The `topic` column in the `signals` table is computed by `api-service`
when a signal is created:

```python
def compute_topic(asset_path: str, signal_type_name: str, signal_name: str) -> str:
    namespace_map = {
        "informative": "measure",
        "operational": "events",
        "descriptive": "$meta",
        "analytic": "$analytics",
    }
    namespace = namespace_map[signal_type_name]
    return f"{asset_path}/{namespace}/{signal_name}"
```

**Example:**
- Asset path: `aeronorth/windfarm_north/sector_a/turbine_03/rotor`
- Signal type: `informative`
- Signal name: `rpm`
- Result: `aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm`

## Reserved topics

| Topic pattern             | Purpose                              |
|---------------------------|--------------------------------------|
| `$SYS/#`                  | EMQX system metrics (built-in)       |
| `+/+/cmd/#`               | Future: command topics (not in MVP)  |

## QoS and retain summary

| Namespace    | QoS (standard) | QoS (buffered) | QoS (critical) | Retain |
|-------------|-----------------|-----------------|-----------------|--------|
| `measure`   | 0               | 0               | 1               | false  |
| `$meta`     | 1               | 1               | 1               | true   |
| `events`    | 1               | 1               | 1               | false  |
| `$analytics`| 0               | 0               | 0               | false  |
