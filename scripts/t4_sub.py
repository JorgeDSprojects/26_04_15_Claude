"""T4 subscriber — subscribes to demo/# and prints all messages.
The retained message must arrive immediately on connect (no new publish needed).
Run twice (Ctrl+C between runs) to verify retained message arrives both times."""
"""T4 subscriber — subscribes to demo/# and prints all messages.
The retained message must arrive immediately on connect (no new publish needed).
Run twice (Ctrl+C between runs) to verify retained message arrives both times."""
import sys
import os
import time  # <-- Añadido el import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect

client = connect()

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_message = on_message
client.subscribe("demo/#", qos=0)
print("Subscribed to demo/# — retained message should appear immediately (Ctrl+C to stop)...")

# 1. Arrancamos el hilo de red
client.loop_start()

# 2. Mantenemos el programa vivo para que dé tiempo a recibir el mensaje
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDeteniendo suscriptor...")
    client.loop_stop()
    client.disconnect()
