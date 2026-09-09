from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app.schemas.travel import TravelRequest
from app.services.planning import PlanningError

router = APIRouter(tags=["planning"])


def error_response(request, code, message, status_code):
    return JSONResponse(status_code=status_code, content={
        "code": code, "message": message, "request_id": request.state.request_id,
    })


async def read_result(request, operation, *args):
    try:
        result = await request.app.state.planning.read(operation, *args)
    except PlanningError as exc:
        return error_response(request, exc.code, exc.message, exc.status_code)
    if result is None:
        return error_response(request, "NOT_FOUND", "未找到对应的本地行程或任务。", 404)
    return result


@router.post("/trips/plan", status_code=202)
async def plan_trip(payload: TravelRequest, request: Request):
    try:
        return await request.app.state.planning.submit(payload)
    except PlanningError as exc:
        return error_response(request, exc.code, exc.message, exc.status_code)


@router.get("/tasks/{task_id}")
async def get_task(task_id: UUID, request: Request):
    return await read_result(request, "task", str(task_id))


@router.get("/trips")
async def list_trips(request: Request, limit: int = Query(20, ge=1, le=50),
                     offset: int = Query(0, ge=0, le=10000)):
    return await read_result(request, "trips", limit, offset)


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: UUID, request: Request):
    return await read_result(request, "trip", str(trip_id))


@router.delete("/trips/{trip_id}", status_code=204)
async def delete_trip(trip_id: UUID, request: Request):
    try:
        await request.app.state.planning.delete_trip(str(trip_id))
    except PlanningError as exc:
        return error_response(request, exc.code, exc.message, exc.status_code)
    return Response(status_code=204)
