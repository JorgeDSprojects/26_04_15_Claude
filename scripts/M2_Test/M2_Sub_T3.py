"""T3 subscriber — subscribes to demo/# and prints all messages.
Run in Terminal A, then run t3_pub.py in Terminal B.
Stop with Ctrl+C."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import connect


# Escuchar TODOS los turbines del sector
# TOPIC = "aeronorth/windfarm_north/sector_a/+/+/measure/#"


TOPICS = [
    "aeronorth/windfarm_north/sector_a/turbine_03/+/measure/#", ]
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

# --- Callbacks para monitorear la conexión ---
def on_connect(client, userdata, flags, rc, *args):
    if rc == 0:
        pass # Conexión silenciosa si todo va bien para no ensuciar la salida
    else:
        print(f"[ERROR] Conexión rechazada. Código: {rc}")

def on_disconnect(client, userdata, rc, *args):
    if rc != 0:
        print(f"[WARN] Desconectado inesperadamente del broker. Código: {rc}")

def on_message(c, userdata, msg):
    print(f"{msg.topic} {msg.payload.decode()}")

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

for topic in TOPICS:
    client.subscribe(topic, qos=QOS)
print(f"Subscribed to {TOPICS} — waiting for messages (Ctrl+C to stop)...")

# --- Solución al cierre silencioso ---
# 1. Arrancamos el bucle de red en segundo plano
client.loop_start()

# 2. Mantenemos el hilo principal vivo esperando mensajes
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    # 3. Al pulsar Ctrl+C, apagamos limpiamente
    print("\nDeteniendo suscriptor...")
    client.loop_stop()
    client.disconnect()