from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app import __version__
from app.db import init_db, log_event
from app.services.aprsis import AprsisClientService
from app.services.aprsis_tx_dispatcher import AprsIsTxDispatcher
from app.services.alerts import expire_aprs_alerts
from app.services.beacon_scheduler import BeaconSchedulerService
from app.services.bulletin_scheduler import BulletinSchedulerService
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.maintenance_scheduler import MaintenanceSchedulerService
from app.services.object_scheduler import ObjectSchedulerService
from app.services.own_alert_scheduler import OwnAlertSchedulerService
from app.services.outbound_runtime import OutboundService
from app.services.radio_activity import RadioActivityAggregatorService
from app.services.rf_tx_dispatcher import RfTxDispatcher
from app.services.traffic import TrafficMonitorService
from app.services.wx_scheduler import WxSchedulerService


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    expire_aprs_alerts()
    aprsis_uplink = AprsisClientService()
    aprsis_tx_dispatcher = AprsIsTxDispatcher(client=aprsis_uplink)
    traffic_monitor = TrafficMonitorService()
    rf_tx_dispatcher = RfTxDispatcher(traffic_monitor=traffic_monitor)
    digi_flow_runtime = DigiFlowRuntimeService(
        aprsis_client=aprsis_uplink,
        aprsis_tx_dispatcher=aprsis_tx_dispatcher,
        rf_tx_dispatcher=rf_tx_dispatcher,
    )
    aprsis_uplink.set_frame_consumer(digi_flow_runtime.enqueue_aprsis_tnc2_frame)
    traffic_monitor.set_frame_consumer(digi_flow_runtime.enqueue_rx_tnc2_frame)
    outbound_service = OutboundService(traffic_monitor=traffic_monitor, digi_flow_runtime=digi_flow_runtime)
    beacon_scheduler = BeaconSchedulerService()
    bulletin_scheduler = BulletinSchedulerService()
    maintenance_scheduler = MaintenanceSchedulerService(poll_interval=30.0)
    object_scheduler = ObjectSchedulerService()
    own_alert_scheduler = OwnAlertSchedulerService()
    wx_scheduler = WxSchedulerService()
    radio_activity_aggregator = RadioActivityAggregatorService()
    app_instance.state.aprsis_uplink = aprsis_uplink
    app_instance.state.aprsis_tx_dispatcher = aprsis_tx_dispatcher
    app_instance.state.digi_flow_runtime = digi_flow_runtime
    app_instance.state.traffic_monitor = traffic_monitor
    app_instance.state.outbound_service = outbound_service
    app_instance.state.rf_tx_dispatcher = rf_tx_dispatcher
    app_instance.state.beacon_scheduler = beacon_scheduler
    app_instance.state.bulletin_scheduler = bulletin_scheduler
    app_instance.state.maintenance_scheduler = maintenance_scheduler
    app_instance.state.object_scheduler = object_scheduler
    app_instance.state.own_alert_scheduler = own_alert_scheduler
    app_instance.state.wx_scheduler = wx_scheduler
    app_instance.state.radio_activity_aggregator = radio_activity_aggregator
    await aprsis_uplink.start()
    await aprsis_tx_dispatcher.start()
    await rf_tx_dispatcher.start()
    await digi_flow_runtime.start()
    await traffic_monitor.start()
    await outbound_service.start()
    await beacon_scheduler.start()
    await bulletin_scheduler.start()
    await maintenance_scheduler.start()
    await object_scheduler.start()
    await own_alert_scheduler.start()
    await wx_scheduler.start()
    await radio_activity_aggregator.start()
    log_event("INFO", "system", "APRSBox core started")
    try:
        yield
    finally:
        await radio_activity_aggregator.stop()
        await wx_scheduler.stop()
        await object_scheduler.stop()
        await own_alert_scheduler.stop()
        await maintenance_scheduler.stop()
        await bulletin_scheduler.stop()
        await beacon_scheduler.stop()
        await outbound_service.stop()
        await traffic_monitor.stop()
        await digi_flow_runtime.wait_until_idle()
        await digi_flow_runtime.stop()
        await aprsis_tx_dispatcher.stop()
        await aprsis_uplink.stop()
        await rf_tx_dispatcher.stop()


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


@app.get("/api/digi-flows/latency")
def digi_flow_latency_snapshot() -> JSONResponse:
    return JSONResponse(app.state.digi_flow_runtime.latency_snapshot())


@app.post("/api/traffic/restart")
async def restart_traffic_monitor() -> JSONResponse:
    await app.state.traffic_monitor.restart()
    log_event("INFO", "traffic", "Traffic monitor runtime restarted by request")
    return JSONResponse({"ok": True})


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
