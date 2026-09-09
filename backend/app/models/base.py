"""Shared model metadata and application-generated UUID/UTC values."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    # MySQL DATETIME has no timezone; all persisted timestamps represent UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)
