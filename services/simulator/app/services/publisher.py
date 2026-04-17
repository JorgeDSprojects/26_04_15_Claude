import asyncio
import json

import aiomqtt
import structlog

from app.config import Settings
from app.services import data_gen

log = structlog.get_logger()

_SIGNALS = [
    ("rotor", "rpm", data_gen.rpm),
    ("nacelle", "wind_speed", data_gen.wind_speed),
    ("generator", "active_power", data_gen.active_power),
]


async def run_publisher(settings: Settings) -> None:
    interval = settings.sim_interval_ms / 1000.0
    asset = settings.sim_asset_path

    async with aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_user,
        password=settings.mqtt_password,
    ) as client:
        log.info("simulator.connected", host=settings.mqtt_host, port=settings.mqtt_port)
        while True:
            for component, signal_name, gen_fn in _SIGNALS:
                topic = f"{asset}/{component}/measure/{signal_name}"
                data = gen_fn()
                await client.publish(topic, json.dumps(data), qos=0, retain=False)
                log.info("simulator.published", topic=topic, val=data["val"], ts=data["ts"])
            await asyncio.sleep(interval)
