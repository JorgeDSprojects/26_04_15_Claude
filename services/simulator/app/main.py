import asyncio
import logging

import structlog

from app.config import Settings
from app.services.publisher import run_publisher

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


async def main() -> None:
    settings = Settings()
    log.info(
        "simulator.starting",
        asset_path=settings.sim_asset_path,
        interval_ms=settings.sim_interval_ms,
    )
    await run_publisher(settings)


if __name__ == "__main__":
    asyncio.run(main())
