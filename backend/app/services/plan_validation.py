"""Deterministic checks over model choices and independently fetched evidence."""

import asyncio
from datetime import datetime, time, timedelta, timezone
from math import isfinite
import re
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.providers.amap import AmapProvider
from app.providers.common import ProviderError
from app.schemas.travel import TravelRequest


# Leave room for packaging a degraded result within the caller's 10s checker.
ROUTE_TIMEOUT_SECONDS = 8
TRANSFER_BUFFER_SECONDS = 600
_MAINLAND_PROVINCES = {"11", "12", "13", "14", "15", "21", "22", "23", "31", "32",
                       "33", "34", "35", "36", "37", "41", "42", "43", "44", "45", "46",
                       "50", "51", "52", "53", "54", "61", "62", "63", "64", "65"}
_SOURCE_PATHS = {"/v3/place/text", "/v3/place/detail", "/v3/weather/weatherInfo",
                 "/v3/direction/walking"}
Text = Annotated[str, Field(strict=True, min_length=1, max_length=2000)]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    poi_id: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    start_time: Annotated[str, Field(strict=True, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    end_time: Annotated[str, Field(strict=True, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    reason: Text


class _Day(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]
    items: Annotated[list[_Item], Field(min_length=1, max_length=6)]


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    summary: Text
    days: Annotated[list[_Day], Field(min_length=1, max_length=7)]
    hotel_id: Annotated[str, Field(strict=True, min_length=1, max_length=80)] | None = None


def _invalid(message: str) -> ProviderError:
    return ProviderError("PLAN_INVALID", message)


def _city_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().removesuffix("市")


def _city_code(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{6}", value):
        raise _invalid("所选地点缺少可核验的行政区码。")
    if value[:2] not in _MAINLAND_PROVINCES:
        raise _invalid("当前行程只支持中国大陆目的地。")
    if value[:2] in {"11", "12", "31", "50"}:
        return value[:2]
    if value[2:4] == "00":
        raise _invalid("仅有省级行政区码，无法核验目的地城市。")
    # Province-administered county-level cities have distinct six-digit codes.
    return value if value[2:4] == "90" else value[:4]


def _candidate_map(value: Any) -> dict[str, dict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _invalid("地点候选数据格式不完整。")
    result = {}
    for item in value:
        key = item.get("id")
        if not isinstance(key, str) or not key:
            continue
        if key in result and result[key] != item:
            raise _invalid("同一地点 ID 返回了不一致的候选数据。")
        result[key] = item
    return result


def _check_poi(poi: dict, request: TravelRequest, city_codes: set[str]) -> None:
    code = _city_code(poi.get("adcode"))
    city_codes.add(code)
    destination = request.destination.strip()
    if re.fullmatch(r"\d{6}", destination):
        matches = code == _city_code(destination)
    else:
        matches = _city_name(poi.get("city")) == _city_name(destination)
    if not matches or len(city_codes) > 1:
        raise _invalid("所选地点不属于已确认的同一目的地城市。")
    if not isinstance(poi.get("name"), str) or not poi["name"].strip():
        raise _invalid("所选地点缺少真实名称。")
    location = poi.get("location")
    if location is not None and not isinstance(location, str):
        raise _invalid("所选地点的坐标格式不完整。")


def _source(value: Any) -> dict | None:
    if not isinstance(value, dict) or value.get("source") != "amap":
        return None
    url = value.get("source_url")
    fetched = value.get("fetched_at")
    if not isinstance(url, str) or not isinstance(fetched, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.netloc != "restapi.amap.com"
            or parsed.path not in _SOURCE_PATHS or parsed.query or parsed.fragment):
        return None
    try:
        fetched_time = datetime.fromisoformat(fetched)
        if fetched_time.tzinfo is None:
            return None
    except ValueError:
        return None
    ttl = (timedelta(hours=24) if parsed.path == "/v3/place/text" else
           timedelta(hours=6) if parsed.path == "/v3/place/detail" else timedelta(minutes=30))
    status = value.get("status", "verified")
    if status not in {"verified", "estimated", "stale", "unknown"}:
        status = "unknown"
    try:
        expiry = datetime.fromisoformat(value["expires_at"]) if "expires_at" in value else fetched_time + ttl
        if expiry.tzinfo is None or expiry < fetched_time:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        expiry = None
        status = "unknown"
    now = _utcnow()
    if fetched_time > now + timedelta(minutes=5):
        status = "unknown"
    elif expiry is not None and expiry <= now:
        status = "stale"
    result = {"source": "amap", "source_url": url, "fetched_at": fetched,
              "expires_at": expiry.isoformat() if expiry is not None else None, "status": status}
    if isinstance(value.get("label"), str):
        result["label"] = value["label"][:200]
    ids = value.get("poi_ids", [])
    if isinstance(ids, list):
        result["poi_ids"] = [item for item in ids if isinstance(item, str)]
    if isinstance(value.get("poi_id"), str):
        result["poi_ids"] = [value["poi_id"]]
    return result


def _valid_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value) and value >= 0
    except OverflowError:
        return False


def _valid_temperature(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value) and -100 <= value <= 70
    except OverflowError:
        return False


async def validate_plan(request: TravelRequest, collected: dict, amap: AmapProvider) -> dict:
    """Reject invalid choices; preserve uncertainty in externally checked facts."""
    try:
        draft = _Draft.model_validate(collected.get("draft"))
    except (AttributeError, ValidationError):
        raise _invalid("生成的行程结构不完整，或包含不支持的字段与时间格式。") from None
    expected_dates = [
        (request.start_date + timedelta(days=offset)).isoformat()
        for offset in range((request.end_date - request.start_date).days + 1)
    ]
    if [day.date for day in draft.days] != expected_dates:
        raise _invalid("行程日期必须按顺序完整覆盖已确认的出行日期。")
    attractions = _candidate_map(collected.get("attractions", []))
    hotels = _candidate_map(collected.get("hotels", []))
    if (not isinstance(collected.get("evidence", []), list)
            or not isinstance(collected.get("opening") or {}, dict)):
        raise _invalid("来源或开放信息格式不完整。")
    window_start = request.daily_window.start
    window_end = request.daily_window.end
    city_codes: set[str] = set()
    evidence: list[dict] = []
    warnings: list[str] = []

    def add_evidence(raw: Any) -> str | None:
        source = _source(raw)
        if source is None:
            return None
        for existing in evidence:
            if {key: value for key, value in existing.items() if key != "id"} == source:
                return existing["id"]
        source["id"] = f"evidence-{len(evidence) + 1}"
        evidence.append(source)
        return source["id"]

    def verified_evidence(ref: str | None) -> bool:
        return any(item["id"] == ref and item["status"] == "verified" for item in evidence)

    for item in collected.get("evidence", []):
        add_evidence(item)
    days = []
    for day_index, day in enumerate(draft.days, 1):
        items = []
        day_warnings = []
        previous_end = window_start
        selected_ids = set()
        for item_index, selected in enumerate(day.items, 1):
            poi = attractions.get(selected.poi_id)
            if poi is None:
                raise _invalid("行程包含未由地图查询返回的景点 ID。")
            _check_poi(poi, request, city_codes)
            if selected.poi_id in selected_ids:
                raise _invalid("同一天不能重复安排同一个景点。")
            selected_ids.add(selected.poi_id)
            start_time, end_time = time.fromisoformat(selected.start_time), time.fromisoformat(selected.end_time)
            if not (window_start <= start_time < end_time <= window_end):
                raise _invalid("活动时间必须处于已确认的每日窗口内，且结束晚于开始。")
            if start_time < previous_end:
                raise _invalid("同一天的活动必须按时间排序且不能重叠。")
            previous_end = end_time
            refs = [entry["id"] for entry in evidence if selected.poi_id in entry.get("poi_ids", [])]
            detail = (collected.get("opening") or {}).get(selected.poi_id)
            detail_ref = add_evidence(detail)
            if detail_ref:
                refs.append(detail_ref)
            if not any(verified_evidence(ref) for ref in refs):
                day_warnings.append(f"{poi['name']}：地点来源缺失或已过期，需要重新核实。")
            # Raw opening-hour text is not a dated guarantee of admission.
            day_warnings.append(f"{poi['name']}：行程当天的营业/开放情况尚未核实，请出发前确认。")
            items.append({
                "id": f"day-{day_index}-item-{item_index}", "poi_id": selected.poi_id,
                "name": poi["name"], "location": poi.get("location"), "address": poi.get("address"),
                "start_time": selected.start_time, "end_time": selected.end_time,
                "reason": selected.reason, "opening_status": "unknown",
                "evidence_refs": list(dict.fromkeys(refs)),
            })
        days.append({"date": day.date, "items": items, "segments": [], "weather": None,
                     "warnings": day_warnings})

    nights = (request.end_date - request.start_date).days
    hotel = None
    if draft.hotel_id is not None:
        if nights == 0 or not request.rooms:
            raise _invalid("无需住宿的行程不能附带酒店安排。")
        chosen = hotels.get(draft.hotel_id)
        if chosen is None:
            raise _invalid("行程包含未由地图查询返回的酒店 ID。")
        _check_poi(chosen, request, city_codes)
        hotel = {"poi_id": draft.hotel_id, "name": chosen["name"], "address": chosen.get("address"),
                 "location": chosen.get("location"), "price": None,
                 "rooms": request.rooms, "nights": nights}
    elif nights and request.rooms:
        warnings.append("尚未取得可用住宿建议，需要另行确认酒店。")

    weather = collected.get("weather")
    weather_ref = add_evidence(weather)
    forecasts_by_date = {}
    if (verified_evidence(weather_ref) and isinstance(weather.get("forecasts"), list)
            and weather.get("source_url") == "https://restapi.amap.com/v3/weather/weatherInfo"):
        for forecast in weather.get("forecasts", []):
            if not isinstance(forecast, dict):
                continue
            try:
                weather_code = _city_code(forecast.get("adcode"))
            except ProviderError:
                continue
            if weather_code not in city_codes:
                continue
            casts = forecast.get("casts")
            if not isinstance(casts, list):
                continue
            for cast in casts:
                valid_cast = isinstance(cast, dict) and isinstance(cast.get("date"), str)
                if valid_cast:
                    for field in ("day_temperature_celsius", "night_temperature_celsius"):
                        if not _valid_temperature(cast.get(field)):
                            valid_cast = False
                    conditions = [cast.get(field) for field in ("day_weather", "night_weather")]
                    if (not all(value is None or isinstance(value, str) for value in conditions)
                            or not any(isinstance(value, str) and value.strip() for value in conditions)):
                        valid_cast = False
                if valid_cast:
                    fields = ("date", "day_weather", "night_weather", "day_temperature_celsius",
                              "night_temperature_celsius", "day_wind", "night_wind",
                              "day_wind_power", "night_wind_power")
                    forecasts_by_date[cast["date"]] = {
                        **{field: cast.get(field) for field in fields},
                        "report_time": forecast.get("report_time"), "evidence_refs": [weather_ref],
                    }
    for day in days:
        day["weather"] = forecasts_by_date.get(day["date"])
        if day["weather"] is None:
            day["warnings"].append("该日期没有可核验的天气预报，不能用其他日期天气替代。")
        else:
            conditions = [day["weather"].get(field) for field in ("day_weather", "night_weather")]
            risky = [value for value in conditions if isinstance(value, str) and any(
                term in value for term in ("大雨", "暴雨", "雷阵雨", "雷雨", "大雪", "暴雪", "台风")
            )]
            if risky:
                day["warnings"].append(
                    f"真实天气预报包含{'、'.join(dict.fromkeys(risky))}，建议减少户外活动并关注当天预警。"
                )

    # Bound the entire route stage, including time waiting for concurrency slots.
    pairs = {}
    for day in days:
        for first, second in zip(day["items"], day["items"][1:]):
            pairs[(first["location"], second["location"])] = None
    semaphore = asyncio.Semaphore(3)

    async def fetch_route(pair):
        if not all(isinstance(location, str) and location for location in pair):
            return
        try:
            async with semaphore:
                pairs[pair] = await amap.walking_route(*pair)
        except ProviderError:
            pass

    try:
        async with asyncio.timeout(ROUTE_TIMEOUT_SECONDS):
            await asyncio.gather(*(fetch_route(pair) for pair in pairs))
    except TimeoutError:
        warnings.append("路线核验超过本次时间限制，未完成的路段已标记未知。")

    for day in days:
        for first, second in zip(day["items"], day["items"][1:]):
            raw = pairs[(first["location"], second["location"])]
            ref = add_evidence(raw)
            distance = raw.get("distance_meters") if isinstance(raw, dict) else None
            duration = raw.get("duration_seconds") if isinstance(raw, dict) else None
            verified = (verified_evidence(ref) and _valid_number(distance) and _valid_number(duration)
                        and duration <= 7 * 24 * 3600
                        and raw.get("source_url") == "https://restapi.amap.com/v3/direction/walking")
            segment = {"from_item_id": first["id"], "to_item_id": second["id"], "mode": "walking",
                       "distance_meters": distance if verified else None,
                       "duration_seconds": duration if verified else None,
                       "status": "verified" if verified else "unknown", "polyline": None,
                       "buffer_minutes": 10, "evidence_refs": [ref] if verified else []}
            if verified:
                segment["polyline"] = raw.get("polyline")
                departure = datetime.fromisoformat(f"{day['date']}T{first['end_time']}")
                arrival = departure + timedelta(seconds=duration + TRANSFER_BUFFER_SECONDS)
                next_start = datetime.fromisoformat(f"{day['date']}T{second['start_time']}")
                segment["message"] = "已核验高德步行估算，另预留 10 分钟缓冲。"
                if arrival > next_start:
                    segment["status"] = "conflict"
                    segment["message"] = f"含 10 分钟缓冲，最早约 {arrival:%m-%d %H:%M} 到达，晚于下一活动开始。"
            else:
                segment["message"] = "未取得完整步行距离与耗时，交通衔接尚未核实。"
            if segment["status"] != "verified":
                day["warnings"].append(f"{first['name']} → {second['name']}：{segment['message']}")
            day["segments"].append(segment)

    unknown_items = ["景点门票", "餐饮", "目的地市内交通"]
    if nights and request.rooms:
        unknown_items.insert(0, "酒店住宿")
    budget_warnings = ["尚未取得可核验的费用报价，无法判断是否符合预算；未知费用不按 0 元计算。",
                       "预算为全体同行人的目的地总支出，不含往返城际交通；精细费用核算属于后续阶段。"]
    warnings.extend(["各景点游览时长为行程建议，不代表营业、预约或入场保证。", *budget_warnings])
    for day in days:
        warnings.extend(f"{day['date']}：{warning}" for warning in day["warnings"])
    warnings = list(dict.fromkeys(warnings))
    return {
        "plan": {"schema_version": 1, "title": draft.title, "summary": draft.summary,
                 "days": days, "hotel": hotel, "evidence": evidence},
        "validation": {"status": "degraded" if warnings else "ready", "warnings": warnings},
        "budget": {"budget_total": format(request.budget_total, ".2f"), "currency": "CNY",
                   "budget_scope": "destination_only", "pricing_status": "not_calculated",
                   "known_total": None, "estimated_total": None,
                   "unknown_items": unknown_items, "warnings": budget_warnings},
    }
