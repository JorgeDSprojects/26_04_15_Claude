import math
import time


def _sine(t: float, midpoint: float, amplitude: float, period_s: float) -> float:
    return midpoint + amplitude * math.sin(2 * math.pi * t / period_s)


def payload(val: float) -> dict:
    return {
        "val": round(val, 2),
        "ts": int(time.time() * 1000),
        "q": 1,
    }


def rpm() -> dict:
    """Rotor RPM: 0–20 RPM, 60 s period."""
    t = time.time()
    return payload(_sine(t, midpoint=10.0, amplitude=10.0, period_s=60.0))


def wind_speed() -> dict:
    """Nacelle wind speed: 3–25 m/s, 90 s period."""
    t = time.time()
    return payload(_sine(t, midpoint=14.0, amplitude=11.0, period_s=90.0))


def active_power() -> dict:
    """Generator active power: 0–2000 kW, 120 s period."""
    t = time.time()
    return payload(_sine(t, midpoint=1000.0, amplitude=1000.0, period_s=120.0))
