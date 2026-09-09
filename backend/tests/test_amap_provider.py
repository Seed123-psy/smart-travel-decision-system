"""Protocol fixtures from Amap's official docs, reviewed 2026-09-09.

Synthetic values below exercise parsing and failure handling, not live accuracy.
"""

import asyncio
from datetime import datetime
import json
import logging
import traceback

import httpx
import pytest

from app.providers.amap import AmapProvider
from app.providers.common import ProviderError


KEY = "fixture-amap-key-not-a-real-credential"


def invoke(handler, method="search_pois", args=("杭州", "西湖"), key=KEY, **kwargs):
    async def run():
        # Deliberately enable redirects on the client; provider must override it.
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=0.1, follow_redirects=True,
        ) as client:
            return await getattr(AmapProvider(key, client), method)(*args, **kwargs)
    return asyncio.run(run())


def response(payload, status=200):
    return lambda request: httpx.Response(status, json=payload)


def success(**data):
    return {"status": "1", "info": "OK", "infocode": "10000", **data}


def test_poi_request_is_city_limited_and_normalizes_unknowns(caplog):
    caplog.set_level(logging.DEBUG, logger="httpx")

    def handler(request):
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "restapi.amap.com"
        assert request.url.path == "/v3/place/text"
        assert dict(request.url.params) == {
            "city": "杭州", "keywords": "西湖", "citylimit": "true",
            "extensions": "all", "offset": "20", "page": "1", "key": KEY, "output": "JSON",
        }
        return httpx.Response(200, json=success(pois=[{
            "id": "synthetic-poi-001", "name": "西湖景区（测试）",
            "location": "120.148,30.245", "adcode": "330106", "address": [],
            "cityname": "杭州市", "type": "风景名胜", "biz_ext": {"cost": "88"},
        }]))

    result = invoke(handler)
    poi = result["pois"][0]
    assert poi["id"] == "synthetic-poi-001"
    assert poi["location"] == "120.148,30.245"
    assert poi["adcode"] == "330106"
    assert poi["address"] is None
    assert poi["opening_hours"] is None
    assert poi["operating_status"] is None
    assert poi["ticket_price_cny"] is None  # Average cost is not a ticket quote.
    assert result["source"] == "amap"
    assert result["source_url"] == "https://restapi.amap.com/v3/place/text"
    assert datetime.fromisoformat(result["fetched_at"]).tzinfo is not None
    assert KEY not in json.dumps(result)
    assert KEY not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_upstream_echoed_key_is_not_returned():
    result = invoke(response(success(pois=[{"name": KEY}])))
    assert result["pois"][0]["name"] == "[REDACTED]"
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("category", ["110000", "100000", "110000|100000"])
def test_poi_types_are_sent_and_actual_typecode_is_preserved(category):
    def handler(request):
        assert request.url.params["types"] == category
        return httpx.Response(200, json=success(pois=[{
            "id": "B00001", "name": "测试地点", "typecode": "110101",
        }]))
    result = invoke(handler, types=category)
    assert result["pois"][0]["typecode"] == "110101"


@pytest.mark.parametrize("typecode", [None, [], "", "   "])
def test_missing_typecode_is_unknown_and_never_inferred_from_name(typecode):
    result = invoke(response(success(pois=[{
        "id": "B00001", "name": "测试公园", "type": "风景名胜", "typecode": typecode,
    }])), types="110000")
    assert result["pois"][0]["typecode"] is None


@pytest.mark.parametrize("category", ["", " ", "1100", "110000|", "景点", 110000])
def test_invalid_type_filters_are_rejected_without_network(category):
    def handler(request):
        pytest.fail("Invalid category must not disable the intended filter")
    with pytest.raises(ProviderError) as raised:
        invoke(handler, types=category)
    assert raised.value.code == "PROVIDER_INVALID_REQUEST"


@pytest.mark.parametrize(("method", "args", "data", "collection"), [
    ("search_pois", ("杭州", "不存在的地点"), {"pois": []}, "pois"),
    ("walking_route", ("120.148,30.245", "120.149,30.246"), {"route": {"paths": []}}, "paths"),
    ("walking_route", ("120.148,30.245", "120.149,30.246"), {"route": []}, "paths"),
    ("weather_forecast", ("330100",), {"forecasts": []}, "forecasts"),
])
def test_empty_results_stay_empty_without_invented_data(method, args, data, collection):
    result = invoke(response(success(**data)), method, args)
    assert result[collection] == []
    if method == "walking_route":
        assert result["distance_meters"] is None
        assert result["duration_seconds"] is None


def test_walking_uses_returned_meters_and_seconds():
    def handler(request):
        assert request.url.path == "/v3/direction/walking"
        assert request.url.params["origin"] == "120.148,30.245"
        assert request.url.params["destination"] == "120.149,30.246"
        return httpx.Response(200, json=success(route={"paths": [
            {"distance": "1200", "duration": "900"},
            {"distance": "1500", "duration": "1000"},
        ]}))
    result = invoke(handler, "walking_route", ("120.148,30.245", "120.149,30.246"))
    assert result["distance_meters"] == 1200
    assert result["duration_seconds"] == 900
    assert len(result["paths"]) == 2


def test_walking_accepts_observed_lowercase_success_info():
    # Protocol shape observed on 2026-09-09; metrics are synthetic.
    payload = {"status": "1", "info": "ok", "infocode": "10000", "count": "1",
               "route": {"origin": "120.148,30.245", "destination": "120.149,30.246",
                         "paths": [{"distance": "1200", "duration": "900", "steps": []}]}}
    result = invoke(response(payload), "walking_route", ("120.148,30.245", "120.149,30.246"))
    assert result["distance_meters"] == 1200
    assert result["duration_seconds"] == 900


def test_walking_geometry_comes_only_from_returned_steps():
    payload = success(route={"paths": [{"distance": "10", "duration": "20", "steps": [
        {"polyline": "120.148,30.245;120.1485,30.2455"},
        {"polyline": "120.1485,30.2455;120.149,30.246"},
    ]}]})
    result = invoke(response(payload), "walking_route", ("120.148,30.245", "120.149,30.246"))
    assert result["polyline"] == "120.148,30.245;120.1485,30.2455;120.149,30.246"
    without_steps = success(route={"paths": [{"distance": "10", "duration": "20"}]})
    result = invoke(response(without_steps), "walking_route", ("120.148,30.245", "120.149,30.246"))
    assert result["polyline"] is None


def test_poi_details_preserve_only_real_opening_text():
    def handler(request):
        assert request.url.path == "/v3/place/detail"
        assert request.url.params["id"] == "B00001"
        return httpx.Response(200, json=success(pois=[{
            "id": "B00001", "name": "测试景点", "biz_ext": {"open_time": "08:00-18:00", "cost": "99"},
        }]))
    result = invoke(handler, "poi_details", ("B00001",))
    assert result["pois"][0]["opening_hours"] == "08:00-18:00"
    assert result["pois"][0]["operating_status"] is None
    assert result["pois"][0]["ticket_price_cny"] is None


def test_poi_details_reject_different_id_and_preserve_empty_result():
    with pytest.raises(ProviderError) as raised:
        invoke(response(success(pois=[{"id": "B00002"}])), "poi_details", ("B00001",))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert invoke(response(success(pois=[])), "poi_details", ("B00001",))["pois"] == []


def test_weather_preserves_date_horizon_and_report_time():
    def handler(request):
        assert request.url.path == "/v3/weather/weatherInfo"
        assert request.url.params["extensions"] == "all"
        assert request.url.params["city"] == "330100"
        return httpx.Response(200, json=success(forecasts=[{
            "city": "杭州市", "adcode": "330100", "province": "浙江",
            "reporttime": "2026-09-09 11:00:00",
            "casts": [{"date": "2026-09-10", "dayweather": "多云", "nightweather": "阴",
                       "daytemp": "29", "nighttemp": "22", "daywind": [], "daypower": "≤3"}],
        }]))
    result = invoke(handler, "weather_forecast", ("330100",))
    forecast = result["forecasts"][0]
    assert forecast["report_time"] == "2026-09-09 11:00:00"
    assert len(forecast["casts"]) == 1
    assert forecast["casts"][0]["date"] == "2026-09-10"
    assert forecast["casts"][0]["day_temperature_celsius"] == 29
    assert forecast["casts"][0]["day_wind"] is None


@pytest.mark.parametrize(("code", "expected", "retryable"), [
    ("10001", "PROVIDER_AUTH_FAILED", False),
    ("10002", "PROVIDER_AUTH_FAILED", False),
    ("10009", "PROVIDER_AUTH_FAILED", False),
    ("10012", "PROVIDER_AUTH_FAILED", False),
    ("10003", "PROVIDER_QUOTA_EXCEEDED", False),
    ("40000", "PROVIDER_QUOTA_EXCEEDED", False),
    ("10020", "PROVIDER_RATE_LIMITED", True),
    ("10016", "PROVIDER_UNAVAILABLE", True),
    ("20000", "PROVIDER_INVALID_REQUEST", False),
    ("20803", "PROVIDER_NO_ROUTE", False),
])
def test_http_200_business_failures_are_not_success(code, expected, retryable):
    with pytest.raises(ProviderError) as raised:
        invoke(response({"status": "0", "info": f"upstream diagnostic {KEY}", "infocode": code}))
    assert raised.value.code == expected
    assert raised.value.retryable is retryable
    assert KEY not in str(raised.value)


@pytest.mark.parametrize(("status", "expected", "retryable"), [
    (401, "PROVIDER_AUTH_FAILED", False), (403, "PROVIDER_AUTH_FAILED", False),
    (429, "PROVIDER_RATE_LIMITED", True), (503, "PROVIDER_UNAVAILABLE", True),
    (400, "PROVIDER_INVALID_REQUEST", False),
])
def test_http_failures_have_safe_messages(status, expected, retryable):
    with pytest.raises(ProviderError) as raised:
        invoke(response({"detail": KEY}, status))
    assert raised.value.code == expected
    assert raised.value.retryable is retryable
    assert KEY not in str(raised.value)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_do_not_expose_request_urls(error_type):
    def handler(request):
        raise error_type(f"failure at {request.url}", request=request)
    with pytest.raises(ProviderError) as raised:
        invoke(handler)
    expected = "PROVIDER_TIMEOUT" if error_type is httpx.ReadTimeout else "PROVIDER_UNAVAILABLE"
    assert raised.value.code == expected
    assert raised.value.retryable is True
    assert KEY not in "".join(traceback.format_exception(raised.value))


def test_redirect_is_never_followed():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": f"https://example.invalid/?key={KEY}"})
    with pytest.raises(ProviderError) as raised:
        invoke(handler)
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [
    [], {}, {"status": "1", "pois": []},
    {"status": "0", "info": "error"},
    {"status": "0", "info": "OK", "infocode": "10000"},
    {"status": "1", "info": "OK", "infocode": "10001", "pois": []},
    success(pois={}), success(pois=["not an object"]),
    success(pois=[{"name": {"nested": "invalid"}}]),
    success(pois=[{"location": "not coordinates"}]),
])
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises(ProviderError) as raised:
        invoke(response(payload))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_html_instead_of_json_is_safe():
    with pytest.raises(ProviderError) as raised:
        invoke(lambda request: httpx.Response(200, text=f"<html>{KEY}</html>"))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert KEY not in str(raised.value)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", True, {}, 10 ** 309])
def test_invalid_distance_is_not_treated_as_zero(value):
    with pytest.raises(ProviderError) as raised:
        invoke(response(success(route={"paths": [{"distance": value, "duration": "10"}]})),
               "walking_route", ("120.148,30.245", "120.149,30.246"))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


@pytest.mark.parametrize(("method", "args"), [
    ("search_pois", (" ", "西湖")),
    ("weather_forecast", ("杭州",)),
    ("walking_route", ("181,30", "120,30")),
    ("walking_route", ("120.1234567,30", "120,30")),
])
def test_invalid_arguments_do_not_send_requests(method, args):
    def handler(request):
        pytest.fail("Invalid arguments must not reach Amap")
    with pytest.raises(ProviderError) as raised:
        invoke(handler, method, args)
    assert raised.value.code == "PROVIDER_INVALID_REQUEST"


@pytest.mark.parametrize(("method", "args"), [
    ("search_pois", ("杭州", "西湖")),
    ("weather_forecast", ("330100",)),
    ("walking_route", ("120,30", "121,30")),
])
def test_missing_key_is_actionable_without_request(method, args):
    def handler(request):
        pytest.fail("An unconfigured provider must not send a request")
    with pytest.raises(ProviderError) as raised:
        invoke(handler, method, args, key="  ")
    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"
