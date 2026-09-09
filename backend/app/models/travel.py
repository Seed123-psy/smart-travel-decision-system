"""P0 persistence models; no providers or Agents write these tables directly."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_uuid, utc_now


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("travelers BETWEEN 1 AND 10", name="ck_trips_travelers"),
        CheckConstraint("budget_total > 0", name="ck_trips_budget_total"),
        CheckConstraint("end_date >= start_date", name="ck_trips_date_order"),
        CheckConstraint("currency = 'CNY'", name="ck_trips_currency"),
        CheckConstraint(
            "budget_scope = 'destination_only'", name="ck_trips_budget_scope"
        ),
        CheckConstraint(
            "current_version IS NULL OR current_version > 0",
            name="ck_trips_current_version",
        ),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["trip_versions.trip_id", "trip_versions.version"],
            name="fk_trips_current_version",
            use_alter=True,
        ),
        Index("ix_trips_created_at", "created_at"),
        Index("ix_trips_id_current_version", "id", "current_version"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    destination: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer)
    budget_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY")
    budget_scope: Mapped[str] = mapped_column(
        String(32), default="destination_only", server_default="destination_only"
    )
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    current_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PlanningTask(Base):
    __tablename__ = "planning_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'degraded', 'failed')",
            name="ck_planning_tasks_status",
        ),
        CheckConstraint(
            "stage IN ('validating', 'collecting', 'planning', 'checking', 'persisting')",
            name="ck_planning_tasks_stage",
        ),
        Index("ix_planning_tasks_trip_created_at", "trip_id", "created_at"),
        Index("ix_planning_tasks_status", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued"
    )
    stage: Mapped[str] = mapped_column(
        String(16), default="validating", server_default="validating"
    )
    trace_id: Mapped[str] = mapped_column(String(36), default=new_uuid)
    deadline_at: Mapped[datetime] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("task_id", "agent_name", "attempt", name="uq_agent_runs_attempt"),
        CheckConstraint("attempt > 0", name="ck_agent_runs_attempt"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'degraded', 'failed', 'skipped')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_agent_runs_duration_ms"
        ),
        Index("ix_agent_runs_task_created_at", "task_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_tasks.id", ondelete="CASCADE")
    )
    agent_name: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TripVersion(Base):
    __tablename__ = "trip_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_trip_versions_version"),
        CheckConstraint(
            "parent_version IS NULL OR (parent_version > 0 AND parent_version < version)",
            name="ck_trip_versions_parent_version",
        ),
        Index("ix_trip_versions_created_at", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_version: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(100), default="initial", server_default="initial")
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
