from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import __version__, get_version
from app.config import settings
from app.db import init_db, log_event
from app.routers import admin, auth, pages
from app.services.content import (
    alert_notification_change_token,
    alert_notification_snapshot,
    monitoring_public_snapshot,
    traffic_snapshot as get_traffic_snapshot,
)
from app.services.alerts import expire_aprs_alerts
from app.services.https_files import https_file_status
from app.services.network_diagnostics import NetworkDiagnosticsCache
from app.services.traffic_stream import TrafficSnapshotBroadcaster


class ForwardedPrefixMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        forwarded_prefix = headers.get(b"x-forwarded-prefix", b"").decode("latin-1").strip()
        if forwarded_prefix:
            scope["root_path"] = forwarded_prefix.rstrip("/")
        await self.app(scope, receive, send)


def get_client_ip(request: Request) -> str:
    client = request.client
    return client.host if client and client.host else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    expire_aprs_alerts()
    app.state.traffic_stream_broadcaster = TrafficSnapshotBroadcaster(
        snapshot_provider=get_traffic_snapshot,
        tick_seconds=settings.traffic_stream_tick_seconds,
        heartbeat_seconds=settings.traffic_stream_heartbeat_seconds,
        max_clients=settings.traffic_stream_max_clients,
    )
    app.state.alert_stream_broadcaster = TrafficSnapshotBroadcaster(
        snapshot_provider=alert_notification_snapshot,
        change_token_provider=alert_notification_change_token,
        tick_seconds=settings.traffic_stream_tick_seconds,
        heartbeat_seconds=settings.traffic_stream_heartbeat_seconds,
        max_clients=settings.traffic_stream_max_clients,
    )
    https_enabled = bool(https_file_status(app.state.settings.ssl_dir)["https_enabled"])
    diagnostics_scheme = "https" if https_enabled else "http"
    diagnostics_port = app.state.settings.web_https_port if https_enabled else app.state.settings.web_http_port
    app.state.network_diagnostics_cache = NetworkDiagnosticsCache(
        scheme=diagnostics_scheme,
        port=diagnostics_port,
        root_path=app.state.settings.root_path,
    )
    await app.state.traffic_stream_broadcaster.start()
    await app.state.alert_stream_broadcaster.start()
    await app.state.network_diagnostics_cache.start()
    log_event("INFO", "system", "APRSBox web application started")
    try:
        yield
    finally:
        await app.state.network_diagnostics_cache.stop()
        await app.state.alert_stream_broadcaster.stop()
        await app.state.traffic_stream_broadcaster.stop()


app = FastAPI(title="APRSBox", version=__version__, lifespan=lifespan, root_path=settings.root_path)
app.add_middleware(ForwardedPrefixMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.proxy_trusted_ips)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

templates = Jinja2Templates(directory=str(settings.templates_dir))
app.state.templates = templates
app.state.settings = settings
app.state.get_client_ip = get_client_ip

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)


@app.middleware("http")
async def audit_write_requests(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/static/"):
        client_ip = get_client_ip(request)
        log_event("INFO", "http", f"{request.method} {request.url.path} -> {response.status_code} from {client_ip}")
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": get_version()}


@app.get("/api/public/monitoring")
def public_monitoring() -> JSONResponse:
    return JSONResponse(monitoring_public_snapshot())
