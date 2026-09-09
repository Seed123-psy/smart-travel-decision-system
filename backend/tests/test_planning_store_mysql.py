"""Real MySQL store checks, isolated by an outer transaction that always rolls back."""

import asyncio
from datetime import datetime, timedelta
import os

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import utc_now
from app.schemas.travel import SHANGHAI, TravelRequest
from app.services.planning_store import PlanningStore

pytestmark = pytest.mark.skipif(not os.getenv("MYSQL_INTEGRATION_URL"), reason="MySQL opt-in required")


def travel_request():
    day = datetime.now(SHANGHAI).date() + timedelta(days=1)
    return TravelRequest(origin="上海", destination="杭州", start_date=day, end_date=day,
                         travelers=2, budget_total="2000.00", defaults_confirmed=True)


def in_transaction(scenario):
    async def run():
        url = make_url(os.environ["MYSQL_INTEGRATION_URL"]).set(drivername="mysql+asyncmy")
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                outer = await connection.begin()
                try:
                    store = PlanningStore(engine)
                    store.sessions = async_sessionmaker(connection, expire_on_commit=False,
                                                        join_transaction_mode="create_savepoint")
                    await scenario(store)
                finally:
                    await outer.rollback()
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_real_store_initial_progress_and_atomic_version():
    async def scenario(store):
        ids = await store.create(travel_request(), utc_now() + timedelta(seconds=60))
        task = await store.task(ids["task_id"])
        assert task["status"] == "queued" and len(task["agents"]) == 5
        assert task["created_at"].endswith("+00:00")
        await store.stage(ids["task_id"], "collecting")
        await store.event(ids["task_id"], "attractions", "running", {"tools": []}, [])
        await store.event(ids["task_id"], "attractions", "succeeded",
                          {"message": "测试夹具", "tools": ["amap.search_pois"]}, [])
        task = await store.task(ids["task_id"])
        assert task["agents"][0]["status"] == "succeeded"
        assert task["agents"][0]["duration_ms"] >= 0
        result = {"plan": {"schema_version": 1, "title": "事务测试 🧪"},
                  "validation": {"status": "degraded", "warnings": ["测试夹具"]},
                  "budget": {"pricing_status": "not_calculated"}}
        await store.finish(ids["task_id"], result)
        trip = await store.trip(ids["trip_id"])
        assert trip["version"] == 1 and trip["plan"] == result["plan"]
        assert trip["request"]["budget_total"] == "2000.00"
        assert trip["latest_task"]["status"] == "degraded"
        assert (await store.task(ids["task_id"]))["result_url"] == f'/api/trips/{ids["trip_id"]}'
    in_transaction(scenario)


def test_real_store_failed_publish_rolls_back_result_and_version():
    async def scenario(store):
        ids = await store.create(travel_request(), utc_now() + timedelta(seconds=60))
        await store.stage(ids["task_id"], "persisting")
        with pytest.raises(Exception):
            await store.finish(ids["task_id"], {
                "plan": {"fixture": True}, "validation": {"status": "illegal-status"}, "budget": {},
            })
        trip = await store.trip(ids["trip_id"])
        assert trip["version"] is None and trip["plan"] is None
        assert trip["latest_task"]["status"] == "running"
        await store.fail(ids["task_id"], "DATABASE_UNAVAILABLE")
        task = await store.task(ids["task_id"])
        assert task["status"] == "failed" and task["result_url"] is None
        assert all(agent["status"] == "skipped" for agent in task["agents"])
    in_transaction(scenario)


def test_real_store_restart_recovery_preserves_finished_agents():
    async def scenario(store):
        ids = await store.create(travel_request(), utc_now() + timedelta(seconds=60))
        await store.stage(ids["task_id"], "collecting")
        await store.event(ids["task_id"], "attractions", "running", {"tools": []}, [])
        await store.event(ids["task_id"], "hotel", "skipped", {"message": "单日无需住宿"}, [])
        await store.recover()
        task = await store.task(ids["task_id"])
        assert task["status"] == "failed" and task["error_code"] == "SERVER_RESTARTED"
        assert task["agents"][0]["status"] == "failed"
        assert task["agents"][1]["status"] == "skipped" and task["agents"][1]["error_code"] is None
        assert (await store.trip(ids["trip_id"]))["version"] is None
    in_transaction(scenario)


def test_real_store_expired_uncertain_commit_becomes_failed():
    async def scenario(store):
        ids = await store.create(travel_request(), utc_now() - timedelta(seconds=1))
        await store.expire()
        task = await store.task(ids["task_id"])
        assert task["status"] == "failed" and task["error_code"] == "TASK_TIMEOUT"
        assert all(agent["status"] == "skipped" for agent in task["agents"])
    in_transaction(scenario)
