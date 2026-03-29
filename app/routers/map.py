from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user
from app.models import UserIdentity
from app.services.map_service import get_map_page_config, get_map_station_payload
from app.template_helpers import build_template_context

router = APIRouter()


@router.get("/map")
def map_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Map",
        current_user=current_user,
        active_nav="map",
        map_config=get_map_page_config(),
    )
    return templates.TemplateResponse("map.html", context)


@router.get("/api/map/stations")
def map_stations(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_station_payload())
