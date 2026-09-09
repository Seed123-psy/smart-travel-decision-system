from fastapi import APIRouter, Request

from app.services.provider_status import configuration_status

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/status")
async def provider_status(request: Request):
    return configuration_status(request.app.state.settings)
