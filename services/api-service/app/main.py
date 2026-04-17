from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin import setup_admin
from app.config import settings
from app.db import engine
from app.routers import asset_types, assets, signal_types, signals

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api_service.startup")
    yield
    await engine.dispose()
    log.info("api_service.shutdown")


app = FastAPI(
    title="AeroNorth UNS API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(asset_types.router)
app.include_router(assets.router)
app.include_router(signal_types.router)
app.include_router(signals.router)

setup_admin(app, engine)


@app.get("/health")
async def health():
    return {"status": "ok"}
