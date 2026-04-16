# CLI Cheatsheet — MQTT exploration with mosquitto clients

This cheatsheet collects the `mosquitto_pub` / `mosquitto_sub` commands used throughout the modules to inspect the broker by hand. It is intentionally minimal — full CLI reference is at <https://mosquitto.org/documentation/>.

## Prerequisites

- The `aeronorth-uns` stack is running: `docker compose up -d mqtt-broker`.
- `mosquitto-clients` is installed locally:
  - **Windows**: install from <https://mosquitto.org/download/> and add the install folder to `PATH`.
  - **Linux**: `sudo apt install mosquitto-clients`.
  - **macOS**: `brew install mosquitto`.
- All commands target `localhost:1883` because the broker exposes that port to the host.

## Subscribe

```bash
# Subscribe to a single topic, verbose (prints topic + payload).
mosquitto_sub -h localhost -p 1883 -t 'demo/hello' -v

# Subscribe to a branch with the multi-level wildcard '#'.
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -v

# Subscribe to a single level with the '+' wildcard.
mosquitto_sub -h localhost -p 1883 -t 'demo/+/temperature' -v

# Subscribe with a specific QoS (0, 1, or 2).
mosquitto_sub -h localhost -p 1883 -t 'demo/#' -q 1 -v
```

## Publish

```bash
# Plain publish (QoS 0, not retained).
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -m '{"val":1}'

# Retained publish — the broker keeps the message and delivers it to
# any new subscriber that matches the topic.
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -m '{"val":1}' -r

# QoS 1 publish (at-least-once delivery).
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -m '{"val":1}' -q 1

# Clear a retained message: publish an empty payload with -r.
mosquitto_pub -h localhost -p 1883 -t 'demo/hello' -r -n
```

## Wildcards quick reference

| Wildcard | Matches                                            | Example                  |
|----------|----------------------------------------------------|--------------------------|
| `+`      | Exactly one topic level                            | `demo/+/temperature`     |
| `#`      | Zero or more levels (must be the last character)   | `demo/#`                 |

## QoS quick reference

| QoS | Guarantee        | Use when                                       |
|-----|------------------|------------------------------------------------|
| 0   | At most once     | Telemetry where the next sample is good enough |
| 1   | At least once    | Events and metadata that must arrive           |
| 2   | Exactly once     | Avoid in IoT — high latency, rarely needed     |

## Retained messages quick reference

- A retained message survives in the broker until a new retained message overwrites it (or an empty retained payload clears it).
- It is delivered immediately to any new subscriber that matches the topic.
- In this project, **only `sync-service` publishes retained messages** (descriptive `$meta` payloads). The `-r` flag is reserved for that service in production code.

## Troubleshooting

```bash
# Is the broker up?
docker compose ps mqtt-broker

# What does EMQX say?
docker compose logs -f mqtt-broker

# Is port 1883 reachable from the host?
# (Linux/macOS)
nc -zv localhost 1883
# (Windows PowerShell)
Test-NetConnection -ComputerName localhost -Port 1883
```

The EMQX dashboard at <http://localhost:18083> (default `admin` / `public`) is the most ergonomic way to see live connections, subscriptions, and retained messages.
