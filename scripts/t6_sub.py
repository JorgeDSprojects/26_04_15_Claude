"""T6 subscriber — subscribes to aeronorth/+/+/+/+/measure/# (single-level wildcards).
Run in Terminal A, then run t6_pub.py in Terminal B.
All 3 turbine messages must appear. Stop with Ctrl+C."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect

PATTERN = "aeronorth/+/+/+/+/measure/#"
client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe(PATTERN, qos=0)
print(f"Subscribed to {PATTERN} — waiting for messages (Ctrl+C to stop)...")
client.loop_forever()
