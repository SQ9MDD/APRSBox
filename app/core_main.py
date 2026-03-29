from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.db import init_db, log_event
from app.services.traffic import TrafficMonitorService


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    traffic_monitor = TrafficMonitorService()
    app_instance.state.traffic_monitor = traffic_monitor
    await traffic_monitor.start()
    log_event("INFO", "system", "APRSBox core started")
    try:
        yield
    finally:
        await traffic_monitor.stop()


app = FastAPI(title="APRSBox Core", version=__version__, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": __version__}


@app.get("/api/traffic")
def traffic_snapshot() -> JSONResponse:
    return JSONResponse(app.state.traffic_monitor.snapshot())
