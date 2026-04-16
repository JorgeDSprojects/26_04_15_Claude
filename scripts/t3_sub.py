"""T3 subscriber — subscribes to demo/# and prints all messages.
Run in Terminal A, then run t3_pub.py in Terminal B.
Stop with Ctrl+C."""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect

TOPIC = "demo/#"
QOS = 0
RETRY_SECONDS = 5


def connect_with_retry():
    while True:
        try:
            return connect()
        except ConnectionError as exc:
            print(f"[WARN] {exc} Retrying in {RETRY_SECONDS}s... (Ctrl+C to stop)")
            time.sleep(RETRY_SECONDS)


client = connect_with_retry()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe(TOPIC, qos=QOS)
print(f"Subscribed to {TOPIC} — waiting for messages (Ctrl+C to stop)...")
client.loop_forever()
