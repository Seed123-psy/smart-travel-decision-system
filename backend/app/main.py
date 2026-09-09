from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.providers import router as providers_router
from app.api.planning import router as planning_router
from app.api.requirements import router as requirements_router
from app.core.config import Settings, get_settings
from app.core.database import create_database_engine
from app.services.planning import PlanningService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database_engine = create_database_engine(config)
        app.state.planning = PlanningService(config, app.state.database_engine)
        try:
            await app.state.planning.recover()
            yield
        finally:
            await app.state.planning.close()
            if app.state.database_engine is not None:
                await app.state.database_engine.dispose()

    application = FastAPI(
        title="智能旅行决策系统 API",
        version="0.1.0",
        description="本地旅行规划：需求确认、多 Agent 生成、真实进度与行程历史。",
        lifespan=lifespan,
    )
    application.state.settings = config
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"] if part != "body")
            message = error["msg"].removeprefix("Value error, ")
            details.append({"field": location or "request", "message": message})
        return JSONResponse(status_code=422, content={
            "code": "VALIDATION_ERROR",
            "message": "请检查旅行需求中的必填项、日期、人数和预算",
            "request_id": request.state.request_id,
            "details": details,
        })

    application.include_router(health_router, prefix="/api")
    application.include_router(providers_router, prefix="/api")
    application.include_router(requirements_router, prefix="/api")
    application.include_router(planning_router, prefix="/api")
    return application


app = create_app()
