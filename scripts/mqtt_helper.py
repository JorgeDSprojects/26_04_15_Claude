"""
Shared MQTT helper for test scripts.
Reads broker credentials from .env in the project root.
"""
import os
import time
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USER = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASSWORD")


def connect(client_id: str | None = None) -> mqtt.Client:
    """Return a connected, authenticated paho Client.
    Caller is responsible for calling client.disconnect()."""
    if not USER or not PASSWORD:
        raise ConnectionError(
            "MQTT_USER and MQTT_PASSWORD must be set in .env"
        )
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id or "",
    )
    client.username_pw_set(USER, PASSWORD)

    connected = {"rc": None}

    def on_connect(c, userdata, flags, reason_code, properties):
        connected["rc"] = reason_code.value if hasattr(reason_code, "value") else int(reason_code)

    client.on_connect = on_connect
    client.connect(HOST, PORT, keepalive=60)
    client.loop_start()

    deadline = time.time() + 10
    while connected["rc"] is None and time.time() < deadline:
        time.sleep(0.05)
    client.loop_stop()

    if connected["rc"] is None:
        raise ConnectionError(f"Timed out connecting to {HOST}:{PORT}")
    if connected["rc"] != 0:
        raise ConnectionError(
            f"Connection refused by broker (rc={connected['rc']}). "
            "Check MQTT_USER / MQTT_PASSWORD in .env."
        )
    return client


def publish(topic: str, payload: str | None, retain: bool = False) -> None:
    """One-shot: connect, publish, disconnect."""
    client = connect()
    client.loop_start()
    info = client.publish(topic, payload, qos=0, retain=retain)
    info.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()


def subscribe(
    topic: str, timeout: float = 5.0, count: int = 1
) -> list[tuple[str, str]]:
    """Connect, wait up to `timeout` seconds for `count` messages.
    Returns list of (topic, payload) tuples. May return fewer than count."""
    messages: list[tuple[str, str]] = []
    done = {"flag": False}

    client = connect()

    def on_message(c, userdata, msg):
        messages.append((msg.topic, msg.payload.decode("utf-8", errors="replace")))
        if len(messages) >= count:
            done["flag"] = True

    client.on_message = on_message
    client.subscribe(topic, qos=0)
    client.loop_start()

    deadline = time.time() + timeout
    while not done["flag"] and time.time() < deadline:
        time.sleep(0.05)

    client.loop_stop()
    client.disconnect()
    return messages
