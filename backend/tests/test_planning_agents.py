"""Synthetic dated fixtures; role tests use no paid model or external map calls."""

import asyncio
from datetime import date
import json

from hello_agents.core.agent import Agent
from hello_agents.tools.base import Tool
import pytest

from app.agents import planning
from app.core.config import Settings
from app.providers.common import ProviderError
from app.schemas.travel import TravelRequest


REFERENCE_DATE = date(2030, 1, 1)


def request(**overrides):
    return TravelRequest.model_validate({
        "origin": "北京", "destination": "杭州", "start_date": "2030-01-02", "end_date": "2030-01-03",
        "travelers": 2, "budget_total": "3000.00", "defaults_confirmed": True, **overrides,
    }, context={"today": REFERENCE_DATE})


def source(**data):
    return {"source": "amap", "source_url": "https://restapi.amap.com/v3/fixture",
            "fetched_at": "2030-01-01T00:00:00+00:00", "expires_at": "2030-01-02T00:00:00+00:00",
            "status": "verified", **data}


def poi(poi_id, name="合成测试地点", typecode="110101"):
    return {"id": poi_id, "name": name, "location": "120.000000,30.000000", "adcode": "330100",
            "address": "合成地址", "type": "风景名胜;公园广场;公园" if typecode.startswith("11") else "合成类别",
            "typecode": typecode, "city": "杭州", "opening_hours": None,
            "operating_status": None, "ticket_price_cny": None}


class FakeAmap:
    def __init__(self):
        self.calls = []
        self.empty_attractions = False

    async def search_pois(self, city, keywords, *, types=None):
        self.calls.append(("search", city, keywords))
        if keywords == "酒店":
            assert types == "100000"
            return source(pois=[poi("HOTEL1", typecode="100101")])
        if keywords == "市政府":
            assert types is None
            return source(pois=[poi("CITY1", typecode="190100")])
        assert types == "110000"
        return source(pois=[] if self.empty_attractions else [poi("POI1"), poi("POI2")])

    async def weather_forecast(self, code):
        self.calls.append(("weather", code))
        return source(forecasts=[{"casts": [{"date": "2030-01-02"}, {"date": "2030-01-03"}]}])

    async def poi_details(self, poi_id):
        self.calls.append(("details", poi_id))
        return source(pois=[poi(poi_id)])


class FakeModel:
    behavior = None
    instances = []

    def __init__(self, *args):
        self._model = "deepseek-v4-flash"
        self.model = self._model
        self.provider = "deepseek"
        self.calls = []
        self.cancelled = []
        self.active = set()
        type(self).instances.append(self)

    async def generate_json(self, messages, *, max_tokens):
        system = messages[0]["content"]
        data = json.loads(messages[1]["content"])
        name = next((name for name, tool in [
            ("attractions", "search_attractions"), ("hotel", "search_hotels"),
            ("weather", "city_weather"), ("opening", "poi_opening_details"),
        ] if f"唯一工具为 {tool}" in system), "planner")
        self.calls.append(name)
        self.active.add(name)
        try:
            if type(self).behavior:
                override = await type(self).behavior(self, name, data)
                if override is not None:
                    return override, {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
            values = {
                "attractions": {"tool": "search_attractions", "keywords": "景点"},
                "hotel": {"tool": "search_hotels", "keywords": "酒店"},
                "weather": {"tool": "city_weather", "keywords": "市政府"},
                "opening": {"tool": "poi_opening_details", "poi_ids": ["POI1", "POI2"]},
            }
            if name == "planner":
                values[name] = {"title": "合成测试行程", "summary": "请确认未知项目",
                    "days": [{"date": day, "items": [{"poi_id": "POI1", "start_time": "09:00",
                        "end_time": "11:00", "reason": "合成测试推荐理由"}]} for day in data["expected_dates"]],
                    "hotel_id": "HOTEL1" if data["hotels"] else None}
            return values[name], {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        except asyncio.CancelledError:
            self.cancelled.append(name)
            raise
        finally:
            self.active.discard(name)


@pytest.fixture(autouse=True)
def isolate_models(monkeypatch):
    FakeModel.instances = []
    FakeModel.behavior = None
    monkeypatch.setattr(planning, "LlmProvider", FakeModel)


def execute(travel_request=None, amap=None, emit_override=None):
    amap = amap or FakeAmap()
    runner = planning.PlanningAgents(Settings(_env_file=None, database_url=""), amap)
    events = []

    async def emit(*args):
        events.append(args)
        if emit_override:
            await emit_override(*args)

    result = asyncio.run(runner.run(travel_request or request(), emit))
    return result, runner, amap, events


def test_real_helloagents_roles_make_bounded_model_and_tool_calls():
    result, runner, amap, events = execute()
    assert set(runner.roles) == {"attractions", "hotel", "weather", "opening", "planner"}
    assert all(isinstance(role, Agent) for role in runner.roles.values())
    assert all(isinstance(role.tool, Tool) for name, role in runner.roles.items() if name != "planner")
    assert len(FakeModel.instances[0].calls) == 5
    assert len(amap.calls) == 6
    assert FakeModel.instances[0].calls.index("opening") > FakeModel.instances[0].calls.index("attractions")
    assert result["draft"]["days"][0]["items"][0]["poi_id"] == "POI1"
    assert result["opening"]["POI1"]["source"] == "amap"
    assert result["hotels"][0]["id"] == "HOTEL1"
    assert all(isinstance(ref, dict) for event in events for ref in event[3])
    assert all(set(event[2]) <= {"message", "tools", "candidate_count", "usage"} for event in events)
    assert {event[0]: event[1] for event in events}["opening"] == "degraded"


def test_three_specialists_overlap_and_opening_waits_for_attractions():
    async def barrier(model, name, data):
        if name in {"attractions", "hotel", "weather"}:
            for _ in range(100):
                if len(set(model.calls) & {"attractions", "hotel", "weather"}) == 3:
                    return
                await asyncio.sleep(0)
            pytest.fail("Initial specialists did not execute concurrently")
        if name == "opening":
            assert "attractions" not in model.active
    FakeModel.behavior = barrier
    execute()


def test_day_trip_skips_hotel_model_and_tool():
    result, runner, amap, events = execute(request(end_date="2030-01-02"))
    assert "hotel" not in FakeModel.instances[0].calls
    assert not any(call[-1] == "酒店" for call in amap.calls)
    assert result["hotels"] == []
    assert result["draft"]["hotel_id"] is None
    assert next(event[1] for event in events if event[0] == "hotel") == "skipped"


def test_no_valid_attractions_never_calls_planner_or_opening():
    amap = FakeAmap()
    amap.empty_attractions = True
    with pytest.raises(ProviderError) as raised:
        execute(amap=amap)
    assert raised.value.code == "NO_CANDIDATES"
    assert "planner" not in FakeModel.instances[0].calls
    assert "opening" not in FakeModel.instances[0].calls


def test_optional_role_failure_is_recorded_without_fake_data():
    async def unavailable(model, name, data):
        if name == "hotel":
            raise ProviderError("PROVIDER_AUTH_FAILED", "synthetic upstream error")
    FakeModel.behavior = unavailable
    result, _, _, events = execute()
    assert result["hotels"] == []
    assert result["draft"]["hotel_id"] is None
    hotel = [event for event in events if event[0] == "hotel"][-1]
    assert hotel[1] == "degraded"
    assert hotel[4] == "PROVIDER_AUTH_FAILED"
    assert "synthetic upstream" not in str(hotel)


def test_tool_decision_cannot_select_an_arbitrary_tool_or_unknown_poi():
    async def wrong_tool(model, name, data):
        if name == "opening":
            return {"tool": "poi_opening_details", "poi_ids": ["FORGED"]}
    FakeModel.behavior = wrong_tool
    result, _, amap, events = execute()
    assert result["opening"] == {}
    assert not any(call[0] == "details" for call in amap.calls)
    assert [event for event in events if event[0] == "opening"][-1][4] == "PROVIDER_INVALID_RESPONSE"


def test_collect_timeout_cancels_optional_work_and_uses_completed_candidates(monkeypatch):
    monkeypatch.setattr(planning, "COLLECT_SECONDS", 0.02)

    async def delay(model, name, data):
        if name == "weather":
            await asyncio.sleep(10)
    FakeModel.behavior = delay
    result, _, _, events = execute()
    assert result["weather"] is None
    assert "weather" in FakeModel.instances[0].cancelled
    assert not FakeModel.instances[0].active
    assert [event for event in events if event[0] == "weather"][-1][4] == "PROVIDER_TIMEOUT"


def test_external_cancellation_propagates_to_all_model_calls():
    async def delay(model, name, data):
        await asyncio.sleep(10)
    FakeModel.behavior = delay

    async def run():
        runner = planning.PlanningAgents(Settings(_env_file=None), FakeAmap())
        async def emit(*args):
            pass
        task = asyncio.create_task(runner.run(request(), emit))
        while not FakeModel.instances or len(FakeModel.instances[0].active) < 3:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not FakeModel.instances[0].active
        assert set(FakeModel.instances[0].cancelled) == {"attractions", "hotel", "weather"}
    asyncio.run(run())


def test_persistence_callback_failure_aborts_instead_of_degrading():
    async def emit(name, status, *args):
        if name == "attractions" and status == "succeeded":
            raise RuntimeError("database write failed")
    with pytest.raises(RuntimeError, match="database write failed"):
        execute(emit_override=emit)
    assert not FakeModel.instances[0].active
    assert "planner" not in FakeModel.instances[0].calls


@pytest.mark.parametrize("change", ["unknown_poi", "unknown_hotel", "missing_day", "out_of_window",
                                        "reversed_time", "overlap", "repeated_poi", "extra_field", "missing_hotel"])
def test_invalid_planner_drafts_fail_before_returning_a_result(change):
    raw = {"title": "测试", "summary": "测试", "hotel_id": "HOTEL1", "days": [
        {"date": day, "items": [{"poi_id": "POI1", "start_time": "09:00", "end_time": "11:00", "reason": "测试"}]}
        for day in ["2030-01-02", "2030-01-03"]]}
    item = raw["days"][0]["items"][0]
    if change == "unknown_poi": item["poi_id"] = "FORGED"
    elif change == "unknown_hotel": raw["hotel_id"] = "FORGED"
    elif change == "missing_day": raw["days"].pop()
    elif change == "out_of_window": item["start_time"] = "08:00"
    elif change == "reversed_time": item["end_time"] = "08:00"
    elif change == "overlap": raw["days"][0]["items"].append({**item, "poi_id": "POI2"})
    elif change == "repeated_poi": raw["days"][0]["items"].append({**item, "start_time": "12:00", "end_time": "13:00"})
    elif change == "extra_field": raw["guaranteed_free"] = True
    elif change == "missing_hotel": raw["hotel_id"] = None

    async def invalid(model, name, data):
        return raw if name == "planner" else None
    FakeModel.behavior = invalid
    with pytest.raises(ProviderError) as raised:
        execute()
    assert raised.value.code == "PLAN_INVALID"


def test_planner_timeout_is_bounded_and_reported(monkeypatch):
    monkeypatch.setattr(planning, "PLANNER_SECONDS", 0.01)

    async def delay(model, name, data):
        if name == "planner": await asyncio.sleep(10)
    FakeModel.behavior = delay
    with pytest.raises(ProviderError) as raised:
        execute()
    assert raised.value.code == "PROVIDER_TIMEOUT"
    assert "planner" in FakeModel.instances[0].cancelled


def test_candidate_limit_and_deduplication_preserve_only_valid_source_pois():
    data = source(pois=[poi("DUP"), poi("DUP"), {"id": "BAD"}] + [poi(f"P{i}") for i in range(30)])
    selected = planning._pois(data, 10)
    assert len(selected) == 10
    assert len({item["id"] for item in selected}) == 10


def test_administrative_names_stations_companies_and_missing_typecodes_are_not_attractions():
    data = source(pois=[
        poi("CITY", "三亚市", "190100"), poi("TRAIN", "三亚站", "150200"),
        poi("BUS", "三亚汽车站", "150400"), poi("COMPANY", "旅游公司", "170200"),
        poi("HOTEL", "海滩酒店", "100101"), {**poi("UNKNOWN"), "typecode": None},
        {**poi("MALFORMED"), "typecode": "11"}, poi("BEACH", "合成海滩", "110208"),
        poi("PARK", "合成公园", "110101"),
    ])
    assert [item["id"] for item in planning._pois(data, 10)] == ["BEACH", "PARK"]
    assert [item["id"] for item in planning._pois(data, 3, type_prefix="10")] == ["HOTEL"]


def test_only_false_attractions_fail_without_planner_or_hidden_second_search():
    class InvalidCategoryAmap(FakeAmap):
        async def search_pois(self, city, keywords, *, types=None):
            if types == "110000":
                self.calls.append(("search", city, keywords))
                return source(pois=[poi("CITY", "三亚市", "190100"), poi("TRAIN", "三亚站", "150200")])
            return await super().search_pois(city, keywords, types=types)

    amap = InvalidCategoryAmap()
    with pytest.raises(ProviderError) as raised:
        execute(amap=amap)
    assert raised.value.code == "NO_CANDIDATES"
    assert "planner" not in FakeModel.instances[0].calls
    assert len([call for call in amap.calls if call[-1] == "景点"]) == 1
