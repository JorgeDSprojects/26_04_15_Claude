"""T4 publisher — publishes {"val":42} to demo/retained with retain=True.
Run once. The broker stores the message for future subscribers."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import publish

publish("demo/retained", '{"val":42}', retain=True)
print("[OK] Retained message published to demo/retained")
