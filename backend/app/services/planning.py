"""One cancellable local job with a shared 60-second budget and persisted progress."""

import asyncio
from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.models.base import utc_now
from app.providers.amap import AmapProvider
from app.providers.common import ProviderError, create_provider_client
from app.services.planning_store import PlanningStore

ERROR_MESSAGES = {
    "TASK_BUSY": "已有行程正在生成，请等待完成后再提交。",
    "TASK_TIMEOUT": "规划超过 60 秒时间预算，请减少天数或稍后重试。",
    "SERVER_RESTARTED": "本地服务已重启，上次规划未完成，请重新生成。",
    "SERVER_STOPPED": "本地服务已停止，规划未完成，请重新生成。",
    "DATABASE_UNAVAILABLE": "本地数据库暂不可用，请检查 MySQL 后重试。",
    "PROVIDER_NOT_CONFIGURED": "请先配置模型与高德 Web 服务后再生成行程。",
    "PROVIDER_TIMEOUT": "外部服务响应超时，请稍后重试。",
    "PROVIDER_AUTH_FAILED": "外部服务鉴权失败，请检查本地密钥和接口权限。",
    "PROVIDER_QUOTA_EXCEEDED": "外部服务余额或配额不足，请检查服务商控制台。",
    "PROVIDER_RATE_LIMITED": "外部服务请求受限，请稍后重试。",
    "PROVIDER_INVALID_REQUEST": "外部服务不接受当前请求，请检查模型或旅行需求。",
    "PROVIDER_INVALID_RESPONSE": "外部服务未返回合规数据，本次未保存有效行程。",
    "PROVIDER_UNAVAILABLE": "外部服务暂时不可用，请稍后重试。",
    "PLAN_INVALID": "未能生成满足日期、地点或时段约束的行程，请调整需求后重试。",
    "NO_CANDIDATES": "未找到有效的目的地景点，请使用中国大陆城市名称重试。",
    "PLANNING_FAILED": "本次规划未完成，请稍后重试。",
    "NOT_FOUND": "未找到对应的本地行程或任务。",
    "TASK_RUNNING": "行程仍在生成中，完成后才能删除。",
}


class PlanningError(Exception):
    def __init__(self, code, status_code=503):
        self.code = code
        self.status_code = status_code
        self.message = ERROR_MESSAGES.get(code, ERROR_MESSAGES["PLANNING_FAILED"])


class PlanningService:
    def __init__(self, settings, engine, *, store=None, agents_factory=None, validator=None,
                 deadline_seconds=60):
        self.settings = settings
        self.store = store if store is not None else (PlanningStore(engine) if engine is not None else None)
        self.agents_factory = agents_factory
        self.validator = validator
        self.deadline_seconds = deadline_seconds
        self._lock = asyncio.Lock()
        self._recovery_lock = asyncio.Lock()
        self._worker = None
        self._handoff = None
        self._active_task_id = None
        self._recovered = False
        self._pending_failures = {}

    async def recover(self):
        async with self._recovery_lock:
            if self.store is None or self._recovered:
                return
            try:
                async with asyncio.timeout(5):
                    await self.store.recover()
                self._recovered = True
            except Exception:
                # Health and form validation remain available during a database outage.
                pass

    async def _prepare(self):
        if self.store is None:
            raise PlanningError("DATABASE_UNAVAILABLE")
        if not self._recovered:
            await self.recover()
            if not self._recovered:
                raise PlanningError("DATABASE_UNAVAILABLE")
        for task_id, code in list(self._pending_failures.items()):
            await self.store.fail(task_id, code)
            self._pending_failures.pop(task_id, None)
        await self.store.expire()

    async def submit(self, request):
        if self._lock.locked():
            raise PlanningError("TASK_BUSY", 409)
        await self._lock.acquire()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.deadline_seconds
        self._handoff = asyncio.create_task(self._accept(request, deadline))
        # A disconnected HTTP caller must not abandon a task after its DB commit.
        self._handoff.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return await asyncio.shield(self._handoff)

    async def _accept(self, request, deadline):
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout(5):
                await self._prepare()
                if not all(value.strip() for value in (
                    self.settings.llm_api_key, self.settings.llm_base_url,
                    self.settings.llm_model, self.settings.amap_web_service_key,
                )):
                    raise PlanningError("PROVIDER_NOT_CONFIGURED")
                identifiers = await self.store.create(
                    request, utc_now() + timedelta(seconds=max(0, deadline - loop.time()))
                )
            self._active_task_id = identifiers["task_id"]
            self._worker = asyncio.create_task(self._run(identifiers["task_id"], request, deadline))
            return identifiers
        except BaseException as exc:
            self._lock.release()
            if isinstance(exc, (PlanningError, asyncio.CancelledError)):
                raise
            raise PlanningError("DATABASE_UNAVAILABLE") from None

    async def _run(self, task_id, request, deadline):
        try:
            # Reserve two seconds for persisting a terminal failure at the deadline.
            async with asyncio.timeout_at(deadline - 2):
                if self.agents_factory is None:
                    from app.agents.planning import PlanningAgents
                    agents_factory = PlanningAgents
                else:
                    agents_factory = self.agents_factory
                if self.validator is None:
                    from app.services.plan_validation import validate_plan
                    validator = validate_plan
                else:
                    validator = self.validator
                await self.store.stage(task_id, "collecting")

                async def emit(name, status, summary, evidence_refs, error_code=None):
                    if name == "planner" and status == "running":
                        await self.store.stage(task_id, "planning")
                    await self.store.event(task_id, name, status, summary, evidence_refs, error_code)

                async with create_provider_client() as client:
                    amap = AmapProvider(self.settings.amap_web_service_key, client)
                    collected = await agents_factory(self.settings, amap).run(request, emit)
                    await self.store.stage(task_id, "checking")
                    async with asyncio.timeout(10):
                        result = await validator(request, collected, amap)
                await self.store.stage(task_id, "persisting")
                await self.store.finish(task_id, result)
        except asyncio.CancelledError:
            await self._record_failure(task_id, "SERVER_STOPPED")
            raise
        except TimeoutError:
            await self._record_failure(task_id, "TASK_TIMEOUT")
        except ProviderError as exc:
            code = exc.code if exc.code in ERROR_MESSAGES else "PLANNING_FAILED"
            await self._record_failure(task_id, code)
        except SQLAlchemyError:
            await self._record_failure(task_id, "DATABASE_UNAVAILABLE")
        except Exception:
            # No raw SDK exception, connection URL, tool output or reasoning in logs/API.
            await self._record_failure(task_id, "PLANNING_FAILED")
        finally:
            self._active_task_id = None
            self._lock.release()

    async def _record_failure(self, task_id, code):
        self._pending_failures[task_id] = code
        try:
            async with asyncio.timeout(2):
                await self.store.fail(task_id, code)
            self._pending_failures.pop(task_id, None)
        except Exception:
            # Retry persistence on the next read after MySQL recovers.
            pass

    async def delete_trip(self, trip_id):
        if self.store is None:
            raise PlanningError("DATABASE_UNAVAILABLE")
        try:
            async with asyncio.timeout(5):
                await self._prepare()
                outcome = await self.store.delete_trip(trip_id)
        except PlanningError:
            raise
        except Exception:
            raise PlanningError("DATABASE_UNAVAILABLE") from None
        if outcome == "running":
            raise PlanningError("TASK_RUNNING", 409)
        if outcome == "not_found":
            raise PlanningError("NOT_FOUND", 404)

    async def close(self):
        if self._handoff and not self._handoff.done():
            self._handoff.cancel()
            try:
                await self._handoff
            except (asyncio.CancelledError, PlanningError):
                pass
        if self._worker and not self._worker.done():
            active_task_id = self._active_task_id
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            # A task cancelled before its first coroutine step never enters _run's finally.
            if self._active_task_id and active_task_id:
                await self._record_failure(active_task_id, "SERVER_STOPPED")
                self._active_task_id = None
                if self._lock.locked():
                    self._lock.release()

    async def read(self, operation, *args):
        try:
            async with asyncio.timeout(5):
                await self._prepare()
                result = await getattr(self.store, operation)(*args)
            if operation == "task" and result and result["error_code"]:
                result["message"] = ERROR_MESSAGES.get(result["error_code"], ERROR_MESSAGES["PLANNING_FAILED"])
            return result
        except PlanningError:
            raise
        except Exception:
            raise PlanningError("DATABASE_UNAVAILABLE") from None
