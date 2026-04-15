"""T6 publisher — publishes 3 turbine measurement messages using real project topic paths."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import publish

messages = [
    ("aeronorth/windfarm/sector_a/turbine_01/rotor/measure/rpm",             '{"val":120}'),
    ("aeronorth/windfarm/sector_a/turbine_01/nacelle/measure/wind_speed",    '{"val":8.5}'),
    ("aeronorth/windfarm/sector_a/turbine_01/generator/measure/active_power",'{"val":2100}'),
]

for topic, payload in messages:
    publish(topic, payload)
    print(f"[OK] Published to {topic}")
