"""T3 subscriber — subscribes to demo/# and prints all messages.
Run in Terminal A, then run t3_pub.py in Terminal B.
Stop with Ctrl+C."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect

client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe("demo/#", qos=0)
print("Subscribed to demo/# — waiting for messages (Ctrl+C to stop)...")
client.loop_forever()
