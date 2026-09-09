from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings

INITIAL_REVISION = "0001_initial"


def create_database_engine(settings: Settings) -> AsyncEngine | None:
    """Create a lazy connection pool; importing the application never creates tables."""
    if not settings.database_url:
        return None
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 3},
    )
