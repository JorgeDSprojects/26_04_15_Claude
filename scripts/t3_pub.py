"""T3 publisher — publishes {"val":1} to demo/hello.
Run in Terminal B while t3_sub.py is running in Terminal A."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mqtt_helper import publish

publish("demo/hello", '{"val":1}')
print("[OK] Published to demo/hello")
