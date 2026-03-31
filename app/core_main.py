from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.db import init_db, log_event
from app.services.beacon_scheduler import BeaconSchedulerService
from app.services.object_scheduler import ObjectSchedulerService
from app.services.outbound_runtime import OutboundService
from app.services.traffic import TrafficMonitorService


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    traffic_monitor = TrafficMonitorService()
    outbound_service = OutboundService()
    beacon_scheduler = BeaconSchedulerService()
    object_scheduler = ObjectSchedulerService()
    app_instance.state.traffic_monitor = traffic_monitor
    app_instance.state.outbound_service = outbound_service
    app_instance.state.beacon_scheduler = beacon_scheduler
    app_instance.state.object_scheduler = object_scheduler
    await traffic_monitor.start()
    await outbound_service.start()
    await beacon_scheduler.start()
    await object_scheduler.start()
    log_event("INFO", "system", "APRSBox core started")
    try:
        yield
    finally:
        await object_scheduler.stop()
        await beacon_scheduler.stop()
        await outbound_service.stop()
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
