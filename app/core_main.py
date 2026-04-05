from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app import __version__
from app.db import init_db, log_event
from app.services.beacon_scheduler import BeaconSchedulerService
from app.services.bulletin_scheduler import BulletinSchedulerService
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.maintenance_scheduler import MaintenanceSchedulerService
from app.services.object_scheduler import ObjectSchedulerService
from app.services.outbound_runtime import OutboundService
from app.services.traffic import TrafficMonitorService


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    digi_flow_runtime = DigiFlowRuntimeService()
    traffic_monitor = TrafficMonitorService(frame_consumer=digi_flow_runtime.enqueue_rx_tnc2_frame)
    outbound_service = OutboundService(traffic_monitor=traffic_monitor)
    beacon_scheduler = BeaconSchedulerService()
    bulletin_scheduler = BulletinSchedulerService()
    maintenance_scheduler = MaintenanceSchedulerService()
    object_scheduler = ObjectSchedulerService()
    app_instance.state.digi_flow_runtime = digi_flow_runtime
    app_instance.state.traffic_monitor = traffic_monitor
    app_instance.state.outbound_service = outbound_service
    app_instance.state.beacon_scheduler = beacon_scheduler
    app_instance.state.bulletin_scheduler = bulletin_scheduler
    app_instance.state.maintenance_scheduler = maintenance_scheduler
    app_instance.state.object_scheduler = object_scheduler
    await digi_flow_runtime.start()
    await traffic_monitor.start()
    await outbound_service.start()
    await beacon_scheduler.start()
    await bulletin_scheduler.start()
    await maintenance_scheduler.start()
    await object_scheduler.start()
    log_event("INFO", "system", "APRSBox core started")
    try:
        yield
    finally:
        await object_scheduler.stop()
        await maintenance_scheduler.stop()
        await bulletin_scheduler.stop()
        await beacon_scheduler.stop()
        await outbound_service.stop()
        await traffic_monitor.stop()
        await digi_flow_runtime.stop()


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


@app.post("/api/digi-flows/test-inject")
async def digi_flows_test_inject(payload: dict[str, object]) -> JSONResponse:
    source_kind = str(payload.get("source_kind") or "receiver_rf").strip()
    source_ref = str(payload.get("source_ref") or "").strip()
    raw_payload = str(payload.get("raw_payload") or payload.get("line") or "").strip()
    frame_uid = payload.get("frame_uid")
    if not source_ref:
        raise HTTPException(status_code=400, detail="source_ref is required.")
    if not raw_payload:
        raise HTTPException(status_code=400, detail="raw_payload is required.")
    if source_kind != "receiver_rf":
        raise HTTPException(status_code=400, detail="Only receiver_rf test injection is implemented in ETAP 2.")

    result = app.state.digi_flow_runtime.enqueue_tnc2_frame(
        source_kind=source_kind,
        source_ref=source_ref,
        raw_payload=raw_payload,
        frame_uid=str(frame_uid).strip() if frame_uid is not None else None,
    )
    return JSONResponse({"ok": True, **result})
