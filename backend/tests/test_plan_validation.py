"""Synthetic provider evidence referenced at 2026-09-09; no live accuracy claim."""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timezone

import pytest

from app.providers.common import ProviderError
from app.schemas.travel import TravelRequest
from app.services import plan_validation
from app.services.plan_validation import validate_plan


@pytest.fixture(autouse=True)
def reference_clock(monkeypatch):
    monkeypatch.setattr(plan_validation, "_utcnow", lambda: datetime(2026, 9, 9, 0, 10, tzinfo=timezone.utc))


def source(path, **extra):
    return {"source": "amap", "source_url": f"https://restapi.amap.com{path}",
            "fetched_at": "2026-09-09T00:00:00+00:00", **extra}


def request(**changes):
    payload = {"origin": "北京", "destination": "杭州", "start_date": "2026-09-10",
               "end_date": "2026-09-11", "travelers": 3, "budget_total": "6000",
               "defaults_confirmed": True, **changes}
    return TravelRequest.model_validate(payload, context={"today": date(2026, 9, 9)})


def poi(number):
    return {"id": f"POI{number}", "name": f"测试景点{number}", "city": "杭州市",
            "adcode": "330106", "location": f"120.{140 + number},30.245", "address": "测试地址"}


def collected():
    attractions = [poi(number) for number in range(1, 5)]
    hotel = {**poi(9), "name": "测试酒店"}
    return {
        "draft": {"title": "杭州两日游", "summary": "按已确认的需求安排景点。", "hotel_id": hotel["id"],
                  "days": [{"date": f"2026-09-{10 + index}", "items": [
                      {"poi_id": f"POI{index * 2 + 1}", "start_time": "09:00", "end_time": "12:00", "reason": "上午游览"},
                      {"poi_id": f"POI{index * 2 + 2}", "start_time": "13:00", "end_time": "16:00", "reason": "下午游览"},
                  ]} for index in range(2)]},
        "attractions": attractions, "hotels": [hotel],
        "weather": source("/v3/weather/weatherInfo", forecasts=[{
            "city": "杭州市", "adcode": "330100", "report_time": "2026-09-09 08:00:00",
            "casts": [{"date": "2026-09-10", "day_weather": "多云", "day_temperature_celsius": 28}],
        }]),
        "opening": {"POI1": source("/v3/place/detail", pois=[{**attractions[0], "opening_hours": "08:00-18:00"}])},
        "evidence": [source("/v3/place/text", poi_ids=[item["id"] for item in attractions] + [hotel["id"]])],
    }


class FakeAmap:
    def __init__(self, *, duration=300, result=None, error=None, delay=0):
        self.duration = duration
        self.result = result
        self.error = error
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.calls = []

    async def walking_route(self, origin, destination):
        self.calls.append((origin, destination))
        self.active += 1
        self.max_active = max(self.active, self.max_active)
        try:
            await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            if self.result is not None:
                return deepcopy(self.result)
            return source("/v3/direction/walking", distance_meters=500,
                          duration_seconds=self.duration, polyline=f"{origin};{destination}")
        finally:
            self.active -= 1


def run(data=None, provider=None, trip=None):
    return asyncio.run(validate_plan(trip or request(), data or collected(), provider or FakeAmap()))


def test_plan_preserves_budget_scope_sources_and_unknowns():
    result = run()
    plan = result["plan"]
    assert plan["schema_version"] == 1
    assert len(plan["days"]) == 2
    assert plan["hotel"]["rooms"] == 2
    assert plan["hotel"]["nights"] == 1
    assert plan["hotel"]["price"] is None
    assert result["validation"]["status"] == "degraded"
    assert result["budget"]["budget_total"] == "6000.00"
    assert result["budget"]["pricing_status"] == "not_calculated"
    assert result["budget"]["known_total"] is None
    assert result["budget"]["estimated_total"] is None
    assert result["budget"]["currency"] == "CNY"
    assert "酒店住宿" in result["budget"]["unknown_items"]
    first, second = plan["days"]
    assert first["weather"]["date"] == "2026-09-10"
    assert second["weather"] is None  # Do not carry forward yesterday's weather.
    assert first["items"][0]["opening_status"] == "unknown"  # Text is not a dated guarantee.
    assert first["items"][0]["evidence_refs"]
    segment = first["segments"][0]
    assert segment["status"] == "verified"
    assert segment["distance_meters"] == 500
    assert segment["duration_seconds"] == 300
    assert segment["buffer_minutes"] == 10
    assert all(ref in {item["id"] for item in plan["evidence"]} for ref in segment["evidence_refs"])


@pytest.mark.parametrize("change", [
    lambda value: value["draft"]["days"][0]["items"][0].update(poi_id="INVENTED"),
    lambda value: value["draft"]["days"][0].update(date="2026-09-12"),
    lambda value: value["draft"]["days"].reverse(),
    lambda value: value["draft"]["days"].pop(),
    lambda value: value["draft"]["days"][0]["items"][0].update(start_time="08:59"),
    lambda value: value["draft"]["days"][0]["items"][0].update(end_time="18:01"),
    lambda value: value["draft"]["days"][0]["items"][0].update(start_time="25:00"),
    lambda value: value["draft"]["days"][0]["items"][0].update(start_time="12:00"),
    lambda value: value["draft"]["days"][0]["items"][1].update(start_time="11:30"),
    lambda value: value["draft"]["days"][0]["items"][1].update(poi_id="POI1"),
    lambda value: value["draft"].update(hotel_id="FAKE-HOTEL"),
    lambda value: value["draft"].update(total_cost=100),
    lambda value: value["attractions"][0].update(city="南京市", adcode="320102"),
    lambda value: value["attractions"][0].update(adcode="320102"),
    lambda value: value["attractions"][0].update(adcode=None),
    lambda value: value["attractions"][0].update(adcode="810001"),
    lambda value: value["attractions"][0].update(adcode="710001"),
    lambda value: value["attractions"][0].update(adcode="820001"),
])
def test_invalid_model_choices_fail_before_route_calls(change):
    data = collected()
    change(data)
    provider = FakeAmap()
    with pytest.raises(ProviderError) as raised:
        run(data, provider)
    assert raised.value.code == "PLAN_INVALID"
    assert provider.calls == []


def test_route_duration_and_explicit_buffer_detect_conflict():
    result = run(provider=FakeAmap(duration=3600))
    segment = result["plan"]["days"][0]["segments"][0]
    assert segment["status"] == "conflict"
    assert "13:10" in segment["message"]
    assert segment["duration_seconds"] == 3600
    assert any("13:10" in warning for warning in result["validation"]["warnings"])


@pytest.mark.parametrize("route", [
    source("/v3/direction/walking", distance_meters=None, duration_seconds=None),
    source("/v3/direction/walking", distance_meters=100, duration_seconds=None),
    {"distance_meters": 100, "duration_seconds": 60},
    source("/v3/direction/walking", distance_meters=100, duration_seconds=float("nan")),
])
def test_incomplete_or_unproven_routes_are_unknown_not_zero(route):
    result = run(provider=FakeAmap(result=route))
    segment = result["plan"]["days"][0]["segments"][0]
    assert segment["status"] == "unknown"
    assert segment["distance_meters"] is None
    assert segment["duration_seconds"] is None
    assert segment["polyline"] is None


def test_provider_failure_degrades_without_exposing_diagnostic():
    error = ProviderError("PROVIDER_TIMEOUT", "private diagnostic", True)
    result = run(provider=FakeAmap(error=error))
    assert result["plan"]["days"][0]["segments"][0]["status"] == "unknown"
    assert "private diagnostic" not in str(result)


def test_route_stage_has_one_total_timeout(monkeypatch):
    monkeypatch.setattr(plan_validation, "ROUTE_TIMEOUT_SECONDS", 0.005)
    provider = FakeAmap(delay=0.1)
    result = run(provider=provider)
    assert provider.active == 0
    assert all(day["segments"][0]["status"] == "unknown" for day in result["plan"]["days"])
    assert any("路线核验超过" in warning for warning in result["validation"]["warnings"])


def test_route_concurrency_is_at_most_three():
    data = collected()
    data["attractions"] = [poi(number) for number in range(1, 7)]
    for index, day in enumerate(data["draft"]["days"]):
        day["items"] = [
            {"poi_id": f"POI{index * 3 + offset + 1}", "start_time": start, "end_time": end, "reason": "建议游览"}
            for offset, (start, end) in enumerate([("09:00", "10:00"), ("11:00", "12:00"), ("13:00", "14:00")])
        ]
    provider = FakeAmap(delay=0.005)
    run(data, provider)
    assert len(provider.calls) == 4
    assert provider.max_active == 3


def test_weather_from_another_city_does_not_prove_trip_weather():
    data = collected()
    data["weather"]["forecasts"][0]["adcode"] = "320100"
    assert all(day["weather"] is None for day in run(data)["plan"]["days"])


def test_heavy_rain_warning_uses_only_matching_real_forecast():
    data = collected()
    data["weather"]["forecasts"][0]["casts"][0]["day_weather"] = "暴雨"
    days = run(data)["plan"]["days"]
    assert any("暴雨" in warning for warning in days[0]["warnings"])
    assert not any("暴雨" in warning for warning in days[1]["warnings"])


def test_different_districts_in_same_city_are_supported():
    data = collected()
    data["attractions"][0]["adcode"] = "330102"
    assert run(data)["plan"]["days"][0]["items"][0]["poi_id"] == "POI1"


@pytest.mark.parametrize(("expiry", "status"), [
    ("2026-09-09T00:10:00+00:00", "unknown"),
    ("2026-09-09T00:10:01+00:00", "verified"),
])
def test_route_expiration_boundary_is_not_verified(expiry, status):
    route = source("/v3/direction/walking", expires_at=expiry, status="verified",
                   distance_meters=500, duration_seconds=300)
    result = run(provider=FakeAmap(result=route))
    assert result["plan"]["days"][0]["segments"][0]["status"] == status
    route_evidence = [item for item in result["plan"]["evidence"] if item["source_url"].endswith("walking")]
    assert route_evidence[0]["expires_at"] == expiry
    assert route_evidence[0]["status"] == ("stale" if status == "unknown" else "verified")


def test_expired_weather_and_invalid_temperatures_are_unknown():
    data = collected()
    data["weather"]["expires_at"] = "2026-09-09T00:10:00+00:00"
    assert run(data)["plan"]["days"][0]["weather"] is None
    data = collected()
    data["weather"]["forecasts"][0]["casts"][0]["day_temperature_celsius"] = float("nan")
    assert run(data)["plan"]["days"][0]["weather"] is None


def test_fractional_confirmed_window_is_respected():
    trip = request(daily_window={"start": "09:00:30", "end": "18:00"})
    with pytest.raises(ProviderError) as raised:
        run(trip=trip)
    assert raised.value.code == "PLAN_INVALID"


def test_single_day_does_not_invent_hotel_costs_or_nights():
    data = collected()
    data["draft"]["days"] = data["draft"]["days"][:1]
    data["draft"]["hotel_id"] = None
    result = run(data, trip=request(end_date="2026-09-10"))
    assert result["plan"]["hotel"] is None
    assert "酒店住宿" not in result["budget"]["unknown_items"]


def test_missing_hotel_stays_unknown_and_same_poi_can_be_revisited_next_day():
    data = collected()
    data["draft"]["hotel_id"] = None
    data["draft"]["days"][1]["items"] = deepcopy(data["draft"]["days"][0]["items"])
    provider = FakeAmap()
    result = run(data, provider)
    assert result["plan"]["hotel"] is None
    assert len(provider.calls) == 1  # Reuse the same real route evidence within this run.
    assert any("住宿" in warning for warning in result["validation"]["warnings"])
