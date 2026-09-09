"""Read-only flight reference search. Cost is never written to a Trip/budget."""

from datetime import date
import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.providers.common import ProviderError, create_provider_client
from app.providers.flights import get_flight_provider

router = APIRouter(tags=["flights"])

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _error(request: Request, code: str, message: str, status_code: int = 503) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={
        "code": code, "message": message, "request_id": request.state.request_id,
    })


@router.get("/flights/search")
async def search_flights(request: Request,
                         origin: str = Query(min_length=3, max_length=3),
                         destination: str = Query(min_length=3, max_length=3),
                         depart_date: str = Query(min_length=10, max_length=10),
                         return_date: str | None = Query(default=None, min_length=10, max_length=10),
                         adults: int = Query(default=1, ge=1, le=9)):
    origin = origin.upper()
    destination = destination.upper()
    if origin == destination:
        return _error(request, "PROVIDER_INVALID_REQUEST", "出发与到达城市不能相同。", 422)
    if not _DATE.fullmatch(depart_date) or (return_date is not None and not _DATE.fullmatch(return_date)):
        return _error(request, "PROVIDER_INVALID_REQUEST", "日期格式须为 YYYY-MM-DD。", 422)
    try:
        depart = date.fromisoformat(depart_date)
        if return_date is not None:
            ret = date.fromisoformat(return_date)
            if ret < depart:
                return _error(request, "PROVIDER_INVALID_REQUEST", "返程日期不能早于去程日期。", 422)
    except ValueError:
        return _error(request, "PROVIDER_INVALID_REQUEST", "日期无效，请检查后重试。", 422)

    try:
        async with create_provider_client() as client:
            provider = get_flight_provider(request.app.state.settings, client)
            data = await provider.search(origin, destination, depart_date, return_date, adults)
    except ProviderError as exc:
        status = 422 if exc.code in {"PROVIDER_INVALID_REQUEST", "NO_CANDIDATES"} else 503
        return _error(request, exc.code, exc.message, status)
    except Exception:
        return _error(request, "PROVIDER_UNAVAILABLE", "航班服务暂时不可用，请稍后重试。")

    result = {
        "mode": data.get("mode", "demo"), "source": data.get("source", "demo"),
        "origin": origin, "destination": destination,
        "depart_date": depart_date, "return_date": return_date,
        "adults": adults, "currency": "CNY",
        "fetched_at": data.get("fetched_at"), "expires_at": data.get("expires_at"),
        "status": data.get("status", "ok"), "summary": data.get("summary", ""),
        "limitations": data.get("limitations", []),
        "outbound": data.get("outbound", []), "inbound": data.get("inbound") or [],
    }
    return result
