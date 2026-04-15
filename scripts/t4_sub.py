"""T4 subscriber — subscribes to demo/# and prints all messages.
The retained message must arrive immediately on connect (no new publish needed).
Run twice (Ctrl+C between runs) to verify retained message arrives both times."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect

client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe("demo/#", qos=0)
print("Subscribed to demo/# — retained message should appear immediately (Ctrl+C to stop)...")
client.loop_forever()
