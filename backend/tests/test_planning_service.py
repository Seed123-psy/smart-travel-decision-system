"""Local lifecycle tests use controlled Agents; no external or paid requests."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.common import ProviderError
from app.schemas.travel import SHANGHAI, TravelRequest
from app.services.planning import PlanningError, PlanningService


def payload():
    day = (datetime.now(SHANGHAI).date() + timedelta(days=1)).isoformat()
    return {"origin": "上海", "destination": "杭州", "start_date": day, "end_date": day,
            "travelers": 2, "budget_total": "2000.00", "defaults_confirmed": True}


def settings(**kwargs):
    return Settings(_env_file=None, database_url="", llm_api_key="test-private-key",
                    llm_base_url="https://example.invalid", llm_model="test",
                    amap_web_service_key="test-map-key", **kwargs)


class MemoryStore:
    def __init__(self):
        self.state = None
        self.calls = []
        self.fail_writes = False

    async def recover(self):
        self.calls.append("recover")

    async def expire(self):
        pass

    async def create(self, request, deadline_at):
        self.calls.append("create")
        self.state = {"task_id": str(uuid4()), "trip_id": str(uuid4()), "status": "queued",
                      "error_code": None, "stage": "validating"}
        return {key: self.state[key] for key in ("task_id", "trip_id", "status")}

    async def stage(self, task_id, stage):
        self.calls.append(stage)
        self.state.update(status="running", stage=stage)

    async def event(self, *args):
        self.calls.append(("event", args[1], args[2]))

    async def finish(self, task_id, result):
        self.calls.append("finish")
        self.state.update(status=result["validation"]["status"])

    async def fail(self, task_id, code):
        if self.fail_writes:
            raise OSError("private database credentials must not escape")
        self.calls.append("fail")
        self.state.update(status="failed", error_code=code)

    async def task(self, task_id):
        return dict(self.state)


class GoodAgents:
    def __init__(self, settings, amap):
        pass

    async def run(self, request, emit):
        await emit("attractions", "running", {"tools": []}, [])
        await emit("attractions", "succeeded", {"tools": ["amap.search_pois"]}, [])
        await emit("planner", "running", {"tools": []}, [])
        await emit("planner", "succeeded", {"tools": []}, [])
        return {"fixture": True}


async def good_validation(request, collected, amap):
    assert collected == {"fixture": True}
    return {"plan": {}, "validation": {"status": "degraded", "warnings": ["营业时间未知"]}, "budget": {}}


def service(store, agents=GoodAgents, **kwargs):
    return PlanningService(settings(), None, store=store, agents_factory=agents,
                           validator=good_validation, **kwargs)


def test_queued_progress_and_result_are_persisted_in_order():
    async def scenario():
        store = MemoryStore()
        runner = service(store)
        created = await runner.submit(TravelRequest.model_validate(payload()))
        assert created["status"] == "queued"
        await runner._worker
        assert store.state["status"] == "degraded"
        assert store.calls.index("create") < store.calls.index("collecting")
        assert store.calls.index("planning") < store.calls.index("checking") < store.calls.index("finish")
        assert not runner._lock.locked()
    asyncio.run(scenario())


def test_concurrent_submit_rejected_and_shutdown_finishes_task():
    class SlowAgents(GoodAgents):
        async def run(self, request, emit):
            await asyncio.Event().wait()

    async def scenario():
        store = MemoryStore()
        runner = service(store, SlowAgents)
        await runner.submit(TravelRequest.model_validate(payload()))
        with pytest.raises(PlanningError) as exc:
            await runner.submit(TravelRequest.model_validate(payload()))
        assert exc.value.code == "TASK_BUSY" and exc.value.status_code == 409
        await asyncio.sleep(0.01)
        await runner.close()
        assert store.state["error_code"] == "SERVER_STOPPED"
        assert not runner._lock.locked()
    asyncio.run(scenario())


def test_deadline_cancels_agent_and_releases_capacity():
    stopped = []

    class SlowAgents(GoodAgents):
        async def run(self, request, emit):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)

    async def scenario():
        store = MemoryStore()
        runner = service(store, SlowAgents, deadline_seconds=2.08)
        await runner.submit(TravelRequest.model_validate(payload()))
        await runner._worker
        assert stopped == [True]
        assert store.state["error_code"] == "TASK_TIMEOUT"
        assert "finish" not in store.calls
        assert not runner._lock.locked()
    asyncio.run(scenario())


@pytest.mark.parametrize("error,expected", [
    (ProviderError("PROVIDER_QUOTA_EXCEEDED", "private upstream response"), "PROVIDER_QUOTA_EXCEEDED"),
    (RuntimeError("private secret"), "PLANNING_FAILED"),
])
def test_errors_are_safe_and_do_not_publish_a_result(error, expected):
    class BadAgents(GoodAgents):
        async def run(self, request, emit):
            raise error

    async def scenario():
        store = MemoryStore()
        runner = service(store, BadAgents)
        created = await runner.submit(TravelRequest.model_validate(payload()))
        await runner._worker
        result = await runner.read("task", created["task_id"])
        assert result["status"] == "failed" and result["error_code"] == expected
        assert "private" not in str(result)
        assert "finish" not in store.calls
    asyncio.run(scenario())


def test_failed_database_write_reconciles_after_recovery():
    class BadAgents(GoodAgents):
        async def run(self, request, emit):
            raise ProviderError("PLAN_INVALID", "invalid fixture")

    async def scenario():
        store = MemoryStore()
        runner = service(store, BadAgents)
        store.fail_writes = True
        created = await runner.submit(TravelRequest.model_validate(payload()))
        await runner._worker
        with pytest.raises(PlanningError) as exc:
            await runner.read("task", created["task_id"])
        assert exc.value.code == "DATABASE_UNAVAILABLE"
        store.fail_writes = False
        result = await runner.read("task", created["task_id"])
        assert result["status"] == "failed" and result["error_code"] == "PLAN_INVALID"
        assert not runner._pending_failures
    asyncio.run(scenario())


def test_database_required_and_invalid_requests_do_not_create_tasks():
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        result = client.post("/api/trips/plan", json=payload())
        assert result.status_code == 503 and result.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "task_id" not in result.json()
        result = client.post("/api/trips/plan", json={**payload(), "defaults_confirmed": False})
        assert result.status_code == 422
        assert client.get("/api/tasks/not-a-uuid").status_code == 422
        assert client.get("/api/trips?limit=0").status_code == 422
        assert client.get("/api/trips").status_code == 503


def test_missing_provider_does_not_persist_and_releases_slot():
    async def scenario():
        store = MemoryStore()
        runner = PlanningService(Settings(_env_file=None, database_url=""), None, store=store)
        with pytest.raises(PlanningError) as exc:
            await runner.submit(TravelRequest.model_validate(payload()))
        assert exc.value.code == "PROVIDER_NOT_CONFIGURED"
        assert "create" not in store.calls and not runner._lock.locked()
    asyncio.run(scenario())


def test_shutdown_during_acceptance_or_worker_records_failure():
    class SlowAgents(GoodAgents):
        async def run(self, request, emit):
            await asyncio.Event().wait()

    async def scenario():
        store = MemoryStore()
        runner = service(store, SlowAgents)
        await runner.submit(TravelRequest.model_validate(payload()))
        await runner.close()
        assert store.state["error_code"] == "SERVER_STOPPED"
        assert not runner._lock.locked()
    asyncio.run(scenario())


def test_cancelled_http_caller_does_not_abandon_committed_task():
    async def scenario():
        committed, release = asyncio.Event(), asyncio.Event()

        class DelayedStore(MemoryStore):
            async def create(self, request, deadline_at):
                ids = await super().create(request, deadline_at)
                committed.set()
                await release.wait()
                return ids

        store = DelayedStore()
        runner = service(store)
        caller = asyncio.create_task(runner.submit(TravelRequest.model_validate(payload())))
        await committed.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert runner._lock.locked()
        release.set()
        await runner._handoff
        await runner._worker
        assert store.state["status"] == "degraded" and not runner._lock.locked()
    asyncio.run(scenario())


def test_http_read_contract_and_missing_resources():
    class Reader:
        async def read(self, operation, *args):
            if operation == "trips":
                return {"items": [], "limit": args[0], "offset": args[1], "has_more": False}
            return None

    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        client.app.state.planning.read = Reader().read
        assert client.get('/api/trips?limit=5&offset=2').json() == {
            "items": [], "limit": 5, "offset": 2, "has_more": False,
        }
        for path in (f"/api/tasks/{uuid4()}", f"/api/trips/{uuid4()}"):
            result = client.get(path)
            assert result.status_code == 404 and result.json()["code"] == "NOT_FOUND"
            assert result.json()["request_id"] == result.headers["X-Request-ID"]
