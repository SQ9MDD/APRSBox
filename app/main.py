from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.config import settings
from app.db import init_db, log_event
from app.routers import admin, auth, pages
from app.services.core_proxy import CoreTrafficProxy
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    core_proxy = CoreTrafficProxy()
    app_instance.state.core_proxy = core_proxy
    await core_proxy.start()
    log_event("INFO", "system", "APRSBox web application started")
    try:
        yield
    finally:
        await core_proxy.stop()


app = FastAPI(title="APRSBox", version=__version__, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

templates = Jinja2Templates(directory=str(settings.templates_dir))
app.state.templates = templates
app.state.settings = settings

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": __version__}
