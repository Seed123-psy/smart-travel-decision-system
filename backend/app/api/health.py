import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import INITIAL_REVISION

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "smart-travel-api", "version": "0.1.0"}


@router.get("/ready")
async def readiness(request: Request):
    engine = request.app.state.database_engine
    if engine is None:
        return JSONResponse(status_code=503, content={
            "code": "DATABASE_NOT_CONFIGURED",
            "message": "请在 backend/.env 配置独立的 MySQL 数据库并执行迁移",
            "request_id": request.state.request_id,
        })
    try:
        async with asyncio.timeout(5):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                revision = (await connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )).scalar_one_or_none()
        if revision != INITIAL_REVISION:
            return JSONResponse(status_code=503, content={
                "code": "DATABASE_MIGRATION_REQUIRED",
                "message": "MySQL 迁移版本不匹配，请运行 alembic upgrade head",
                "request_id": request.state.request_id,
            })
    except Exception:
        # Never expose connection strings, driver errors or account names to a browser.
        return JSONResponse(status_code=503, content={
            "code": "DATABASE_UNAVAILABLE",
            "message": "MySQL 连接或迁移检查失败，请检查本地配置和数据库初始化",
            "request_id": request.state.request_id,
        })
    return {"status": "ready", "database": "mysql", "revision": revision}
