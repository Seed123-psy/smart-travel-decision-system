"""Transaction boundaries for local planning; Agents never receive a database session."""

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import INITIAL_REVISION
from app.models.base import new_uuid, utc_now
from app.models.travel import AgentRun, PlanningTask, Trip, TripVersion

AGENT_NAMES = ("attractions", "hotel", "weather", "opening", "planner")
TERMINAL = {"ready", "degraded", "failed"}


def iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class PlanningStore:
    def __init__(self, engine):
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def recover(self):
        async with self.sessions.begin() as session:
            revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            if revision != INITIAL_REVISION:
                raise RuntimeError("Database migration required")
            tasks = (await session.scalars(select(PlanningTask).where(
                PlanningTask.status.in_(("queued", "running"))
            ))).all()
            for task in tasks:
                await self._fail(session, task, "SERVER_RESTARTED")

    async def create(self, request, deadline_at):
        trip_id, task_id = new_uuid(), new_uuid()
        async with self.sessions.begin() as session:
            session.add(Trip(
                id=trip_id, destination=request.destination, start_date=request.start_date,
                end_date=request.end_date, travelers=request.travelers,
                budget_total=request.budget_total, request_json=request.model_dump(mode="json"),
            ))
            await session.flush()
            session.add(PlanningTask(id=task_id, trip_id=trip_id, deadline_at=deadline_at))
            await session.flush()
            session.add_all([AgentRun(task_id=task_id, agent_name=name) for name in AGENT_NAMES])
        return {"task_id": task_id, "trip_id": trip_id, "status": "queued"}

    async def expire(self):
        # Also reconciles uncertain commits after a timed-out creation/connection loss.
        async with self.sessions.begin() as session:
            tasks = (await session.scalars(select(PlanningTask).where(
                PlanningTask.status.in_(("queued", "running")),
                PlanningTask.deadline_at <= utc_now(),
            ).with_for_update())).all()
            for task in tasks:
                await self._fail(session, task, "TASK_TIMEOUT")

    async def stage(self, task_id, stage):
        async with self.sessions.begin() as session:
            task = await session.get(PlanningTask, task_id)
            task.status, task.stage = "running", stage

    async def event(self, task_id, name, status, summary, evidence, error_code=None):
        if name not in AGENT_NAMES or status not in {
            "running", "succeeded", "degraded", "failed", "skipped"
        }:
            raise ValueError("Invalid Agent event")
        async with self.sessions.begin() as session:
            run = (await session.scalars(select(AgentRun).where(
                AgentRun.task_id == task_id, AgentRun.agent_name == name, AgentRun.attempt == 1
            ))).one()
            if run.status not in {"queued", "running"}:
                raise ValueError("Agent already finished")
            now = utc_now()
            if status == "running":
                run.started_at = now
            else:
                run.finished_at = now
                run.duration_ms = max(0, int((now - (run.started_at or now)).total_seconds() * 1000))
            run.status = status
            run.summary = summary
            run.evidence_refs = evidence
            run.error_code = error_code

    async def finish(self, task_id, result):
        async with self.sessions.begin() as session:
            task = await session.get(PlanningTask, task_id, with_for_update=True)
            if task.status != "running":
                raise ValueError("Task is not running")
            trip = await session.get(Trip, task.trip_id, with_for_update=True)
            session.add(TripVersion(
                trip_id=trip.id, version=1, reason="initial",
                plan_json=result["plan"], validation_json=result["validation"],
                budget_json=result["budget"],
            ))
            await session.flush()
            trip.current_version = 1
            task.status = result["validation"]["status"]
            task.stage = "persisting"
            task.finished_at = utc_now()

    async def _fail(self, session, task, code):
        if task.status in TERMINAL:
            return
        task.status, task.error_code, task.finished_at = "failed", code, utc_now()
        runs = (await session.scalars(select(AgentRun).where(
            AgentRun.task_id == task.id, AgentRun.status.in_(("queued", "running"))
        ))).all()
        for run in runs:
            run.status = "failed" if run.started_at else "skipped"
            run.finished_at, run.error_code = task.finished_at, code
            run.duration_ms = max(0, int((run.finished_at - (run.started_at or run.finished_at)).total_seconds() * 1000))
            run.summary = {"message": "规划已结束，此步骤未完成。", "tools": []}

    async def fail(self, task_id, code):
        async with self.sessions.begin() as session:
            task = await session.get(PlanningTask, task_id, with_for_update=True)
            if task:
                await self._fail(session, task, code)

    async def task(self, task_id):
        async with self.sessions() as session:
            task = await session.get(PlanningTask, task_id)
            if not task:
                return None
            runs = (await session.scalars(select(AgentRun).where(
                AgentRun.task_id == task_id
            ).order_by(AgentRun.attempt))).all()
            order = {name: index for index, name in enumerate(AGENT_NAMES)}
            runs = sorted(runs, key=lambda run: (order.get(run.agent_name, 99), run.attempt))
            return {
                "task_id": task.id, "trip_id": task.trip_id, "status": task.status,
                "stage": task.stage, "created_at": iso(task.created_at),
                "finished_at": iso(task.finished_at), "error_code": task.error_code,
                "message": None,
                "result_url": f"/api/trips/{task.trip_id}" if task.status in {"ready", "degraded"} else None,
                "agents": [{
                    "agent_name": run.agent_name, "status": run.status, "attempt": run.attempt,
                    "started_at": iso(run.started_at), "finished_at": iso(run.finished_at),
                    "duration_ms": run.duration_ms, "summary": run.summary,
                    "evidence_refs": run.evidence_refs, "error_code": run.error_code,
                } for run in runs],
            }

    async def trip(self, trip_id):
        async with self.sessions() as session:
            trip = await session.get(Trip, trip_id)
            if not trip:
                return None
            version = await session.get(TripVersion, (trip.id, trip.current_version)) if trip.current_version else None
            task = (await session.scalars(select(PlanningTask).where(
                PlanningTask.trip_id == trip.id
            ).order_by(PlanningTask.created_at.desc(), PlanningTask.id.desc()).limit(1))).first()
            return {
                "trip_id": trip.id, "request": trip.request_json, "version": trip.current_version,
                "plan": version.plan_json if version else None,
                "validation": version.validation_json if version else None,
                "budget": version.budget_json if version else None,
                "latest_task": {"task_id": task.id, "status": task.status} if task else None,
                "created_at": iso(trip.created_at),
            }

    async def trips(self, limit, offset):
        async with self.sessions() as session:
            rows = (await session.scalars(select(Trip).order_by(
                Trip.created_at.desc(), Trip.id.desc()
            ).offset(offset).limit(limit + 1))).all()
            items = []
            for trip in rows[:limit]:
                task = (await session.scalars(select(PlanningTask).where(
                    PlanningTask.trip_id == trip.id
                ).order_by(PlanningTask.created_at.desc(), PlanningTask.id.desc()).limit(1))).first()
                items.append({
                    "trip_id": trip.id, "destination": trip.destination,
                    "start_date": trip.start_date.isoformat(), "end_date": trip.end_date.isoformat(),
                    "travelers": trip.travelers, "budget_total": str(trip.budget_total),
                    "version": trip.current_version, "status": task.status if task else "failed",
                    "created_at": iso(trip.created_at),
                })
            return {"items": items, "limit": limit, "offset": offset, "has_more": len(rows) > limit}
