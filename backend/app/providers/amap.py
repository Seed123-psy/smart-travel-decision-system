"""Small, read-only adapters for documented Amap Web Service endpoints."""

from datetime import date, datetime, timedelta, timezone
import logging
import math
import re
from typing import Any

import httpx

from app.providers.common import ProviderError


AMAP_ORIGIN = "https://restapi.amap.com"
_KEY_QUERY = re.compile(r"([?&]key=)[^&\s\"']+", re.IGNORECASE)
_COORDINATES = re.compile(r"-?\d{1,3}(?:\.\d{1,6})?,-?\d{1,2}(?:\.\d{1,6})?")


class _RedactQueryKeys(logging.Filter):
    """httpx logs request URLs at INFO, including Amap's mandatory query key."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        sanitized = _KEY_QUERY.sub(r"\1[REDACTED]", message)
        if sanitized != message:
            record.msg = sanitized
            record.args = ()
        return True


def _install_log_filter() -> None:
    # Filters on parent loggers do not filter propagated child records.
    for name in ("httpx", "httpcore", "httpcore.connection", "httpcore.http11", "httpcore.http2"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, _RedactQueryKeys) for item in logger.filters):
            logger.addFilter(_RedactQueryKeys())


def _invalid_response() -> ProviderError:
    return ProviderError("PROVIDER_INVALID_RESPONSE", "高德返回的数据格式不符合接口约定。")


def _text(value: Any) -> str | None:
    # Amap explicitly documents [] in place of unavailable string fields.
    if value is None or value == [] or value == "":
        return None
    if not isinstance(value, str):
        raise _invalid_response()
    return value.strip() or None


def _number(value: Any, *, nonnegative: bool = False) -> float | int | None:
    if value is None or value == [] or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise _invalid_response()
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise _invalid_response() from None
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise _invalid_response()
    return int(number) if number.is_integer() else number


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _invalid_response()
    return value


def _location(value: Any) -> str | None:
    result = _text(value)
    if result is None:
        return None
    if not _COORDINATES.fullmatch(result):
        raise _invalid_response()
    longitude, latitude = map(float, result.split(","))
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise _invalid_response()
    return result


def _poi(item: dict[str, Any], *, details: bool = False) -> dict[str, Any]:
    extension = item.get("biz_ext")
    opening_hours = None
    if details and isinstance(extension, dict):
        opening_hours = _text(extension.get("open_time")) or _text(extension.get("opentime"))
    return {
        "id": _text(item.get("id")), "name": _text(item.get("name")),
        "location": _location(item.get("location")), "adcode": _text(item.get("adcode")),
        "address": _text(item.get("address")), "type": _text(item.get("type")),
        "typecode": _text(item.get("typecode")),
        "city": _text(item.get("cityname")), "opening_hours": opening_hours,
        "operating_status": None, "ticket_price_cny": None,
    }


def _walking_geometry(item: dict[str, Any]) -> str | None:
    points: list[str] = []
    for step in _items(item.get("steps", [])):
        polyline = _text(step.get("polyline"))
        if polyline:
            for value in polyline.split(";"):
                point = _location(value)
                if point and (not points or points[-1] != point):
                    points.append(point)
    return ";".join(points) if points else None


class AmapProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        self._api_key = api_key.strip()
        self._client = client
        _install_log_filter()

    def _configured(self) -> None:
        if not self._api_key:
            raise ProviderError("PROVIDER_NOT_CONFIGURED", "尚未配置高德 Web 服务密钥。")

    @staticmethod
    def _query_text(value: str, label: str, limit: int = 100) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            raise ProviderError("PROVIDER_INVALID_REQUEST", f"{label}不能为空或超过 {limit} 个字符。")
        return value.strip()

    @staticmethod
    def _business_error(code: str) -> ProviderError:
        if code in {"10001", "10002", "10005", "10006", "10007", "10008", "10009",
                    "10012", "10013", "10026", "10041", "20011", "40002"}:
            return ProviderError("PROVIDER_AUTH_FAILED", "高德密钥、平台类型或接口权限不可用，请检查配置。")
        if code in {"10003", "10010", "10044", "10045", "40000", "40003"}:
            return ProviderError("PROVIDER_QUOTA_EXCEEDED", "高德调用配额或余额已用尽，请检查控制台。")
        if code in {"10004", "10014", "10015", "10019", "10020", "10021", "10029"}:
            return ProviderError("PROVIDER_RATE_LIMITED", "高德请求过于频繁，请稍后重试。", True)
        if code in {"20000", "20001", "20002", "20012"}:
            return ProviderError("PROVIDER_INVALID_REQUEST", "高德不接受当前查询参数。")
        if code in {"20800", "20801", "20802", "20803"}:
            return ProviderError("PROVIDER_NO_ROUTE", "高德无法提供这些地点之间的步行路线。")
        return ProviderError("PROVIDER_UNAVAILABLE", "高德服务暂时不可用，请稍后重试。", True)

    async def _request(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self._configured()
        try:
            response = await self._client.get(
                AMAP_ORIGIN + path,
                params={**params, "key": self._api_key, "output": "JSON"},
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "高德请求超时，请稍后重试。", True) from None
        except httpx.RequestError:
            # httpx exceptions can contain a full request URL and credential.
            raise ProviderError("PROVIDER_UNAVAILABLE", "无法连接高德服务，请稍后重试。", True) from None
        if response.status_code in {401, 403}:
            raise self._business_error("10012")
        if response.status_code == 429:
            raise self._business_error("10004")
        if response.status_code >= 500:
            raise ProviderError("PROVIDER_UNAVAILABLE", "高德服务暂时不可用，请稍后重试。", True)
        if 400 <= response.status_code < 500:
            raise ProviderError("PROVIDER_INVALID_REQUEST", "高德不接受当前查询请求。")
        if response.status_code != 200 or len(response.content) > 2_000_000:
            raise _invalid_response()
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            raise _invalid_response() from None
        if not isinstance(payload, dict):
            raise _invalid_response()
        status = payload.get("status")
        if status == "0":
            code = payload.get("infocode")
            if (not isinstance(code, str) or not re.fullmatch(r"\d{5}", code)
                    or code == "10000"):
                raise _invalid_response()
            raise self._business_error(code)
        info = payload.get("info")
        # The live v3 walking endpoint returns lowercase "ok", unlike the
        # uppercase "OK" documented and used by POI/weather responses.
        if (status != "1" or not isinstance(info, str) or info.lower() != "ok"
                or payload.get("infocode", "10000") != "10000"):
            raise _invalid_response()
        return payload

    def _result(self, path: str, **data: Any) -> dict[str, Any]:
        fetched = datetime.now(timezone.utc)
        validity = (timedelta(hours=24) if path == "/v3/place/text" else
                    timedelta(hours=6) if path == "/v3/place/detail" else timedelta(minutes=30))
        result = {
            "source": "amap",
            "source_url": AMAP_ORIGIN + path,
            "fetched_at": fetched.isoformat(),
            "expires_at": (fetched + validity).isoformat(),
            "status": "verified",
            **data,
        }

        def redact(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace(self._api_key, "[REDACTED]")
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, dict):
                return {key: redact(item) for key, item in value.items()}
            return value

        return redact(result)

    async def search_pois(self, city: str, keywords: str, *, types: str | None = None) -> dict[str, Any]:
        self._configured()
        city = self._query_text(city, "城市", 80)
        keywords = self._query_text(keywords, "搜索关键词")
        path = "/v3/place/text"
        params = {
            "city": city, "keywords": keywords, "citylimit": "true",
            "extensions": "all", "offset": "20", "page": "1",
        }
        if types is not None:
            if not isinstance(types, str) or not re.fullmatch(r"\d{6}(?:\|\d{6}){0,4}", types.strip()):
                raise ProviderError("PROVIDER_INVALID_REQUEST", "POI 类型须为六位分类代码，多个类别用 | 分隔。")
            params["types"] = types.strip()
        payload = await self._request(path, params)
        pois = [_poi(item) for item in _items(payload.get("pois"))]
        return self._result(
            path, pois=pois, summary=f"本次查询返回 {len(pois)} 个地点。",
            limitations=["仅返回首批最多 20 个地点，不是城市全量清单。",
                         "POI 信息不能证明开放状态、营业时间或实时门票价格。"],
        )

    async def poi_details(self, poi_id: str) -> dict[str, Any]:
        self._configured()
        poi_id = self._query_text(poi_id, "地点 ID", 80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", poi_id):
            raise ProviderError("PROVIDER_INVALID_REQUEST", "地点 ID 格式不正确。")
        path = "/v3/place/detail"
        payload = await self._request(path, {"id": poi_id, "extensions": "all"})
        pois = [_poi(item, details=True) for item in _items(payload.get("pois"))]
        if any(item["id"] != poi_id for item in pois):
            raise _invalid_response()
        return self._result(
            path, pois=pois, summary=f"本次地点详情查询返回 {len(pois)} 条记录。",
            limitations=["地点详情可能需要单独开通权限。",
                         "返回的营业时间文本仅供参考，不能保证行程当天开放或实时票价。"],
        )

    async def walking_route(self, origin: str, destination: str) -> dict[str, Any]:
        self._configured()
        try:
            origin = _location(origin)
            destination = _location(destination)
            if origin is None or destination is None:
                raise _invalid_response()
        except ProviderError:
            raise ProviderError(
                "PROVIDER_INVALID_REQUEST", "步行起终点需为合法经纬度，格式为经度,纬度，最多六位小数。",
            ) from None
        path = "/v3/direction/walking"
        payload = await self._request(path, {"origin": origin, "destination": destination})
        route = payload.get("route")
        if route == []:
            route = {"paths": []}
        if not isinstance(route, dict):
            raise _invalid_response()
        paths = [
            {"distance_meters": _number(item.get("distance"), nonnegative=True),
             "duration_seconds": _number(item.get("duration"), nonnegative=True),
             "polyline": _walking_geometry(item)}
            for item in _items(route.get("paths"))
        ]
        primary = paths[0] if paths else {
            "distance_meters": None, "duration_seconds": None, "polyline": None,
        }
        summary = "未查询到可用步行路线。"
        if paths:
            summary = ("已取得步行路线估算。" if primary["distance_meters"] is not None
                       and primary["duration_seconds"] is not None
                       else "查询到步行方案，但部分距离或时间数据缺失。")
        return self._result(
            path, origin=origin, destination=destination, **primary, paths=paths,
            summary=summary,
            limitations=["距离与时间为高德步行估算，不包含景区排队、游览或其他交通方式。"],
        )

    async def weather_forecast(self, city: str) -> dict[str, Any]:
        self._configured()
        if not isinstance(city, str) or not re.fullmatch(r"\d{6}", city):
            raise ProviderError("PROVIDER_INVALID_REQUEST", "天气查询需要六位城市行政区码。")
        path = "/v3/weather/weatherInfo"
        payload = await self._request(path, {"city": city, "extensions": "all"})
        forecasts = []
        for item in _items(payload.get("forecasts")):
            casts = []
            for cast in _items(item.get("casts")):
                forecast_date = _text(cast.get("date"))
                if forecast_date is not None:
                    try:
                        if date.fromisoformat(forecast_date).isoformat() != forecast_date:
                            raise ValueError
                    except ValueError:
                        raise _invalid_response() from None
                casts.append({
                    "date": forecast_date,
                    "day_weather": _text(cast.get("dayweather")),
                    "night_weather": _text(cast.get("nightweather")),
                    "day_temperature_celsius": _number(cast.get("daytemp")),
                    "night_temperature_celsius": _number(cast.get("nighttemp")),
                    "day_wind": _text(cast.get("daywind")),
                    "night_wind": _text(cast.get("nightwind")),
                    "day_wind_power": _text(cast.get("daypower")),
                    "night_wind_power": _text(cast.get("nightpower")),
                })
            forecasts.append({
                "city": _text(item.get("city")),
                "adcode": _text(item.get("adcode")),
                "province": _text(item.get("province")),
                "report_time": _text(item.get("reporttime")),
                "casts": casts,
            })
        return self._result(
            path, forecasts=forecasts,
            summary=f"取得 {sum(len(item['casts']) for item in forecasts)} 条日期天气预报。",
            limitations=["预报仅适用于返回日期，不能推断整个行程天气；无数据的日期应标记未知。",
                         "report_time 为高德数据发布时间，fetched_at 为本次查询时间。"],
        )
