"""Inspect configuration; use --live explicitly to make small external API calls."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.core.config import Settings
from app.providers.common import ProviderError, create_provider_client
from app.services.provider_status import configuration_status


def summarize_route(value: dict) -> dict:
    fields = ("distance_meters", "duration_seconds")
    if any(value.get(field) is None for field in fields):
        raise ProviderError("PROVIDER_NO_ROUTE", "本次检测未取得完整的步行距离与时间。")
    return {field: value[field] for field in fields}


def summarize_forecasts(value: dict) -> dict:
    days = sum(len(item["casts"]) for item in value["forecasts"])
    if days == 0:
        raise ProviderError("PROVIDER_NO_FORECAST", "本次检测未取得日期天气预报。")
    return {"forecast_days": days}


async def check_one(name, operation, summarize):
    started = perf_counter()
    try:
        async with asyncio.timeout(20):
            result = await operation()
        return {
            "name": name, "status": "succeeded",
            "duration_ms": round((perf_counter() - started) * 1000),
            "summary": summarize(result),
        }, result
    except ProviderError as error:
        code, message, retryable = error.code, error.message, error.retryable
    except TimeoutError:
        code, message, retryable = "PROVIDER_TIMEOUT", "服务检测超过时间限制", True
    except Exception:
        # Never expose upstream exceptions, request headers, or credential-bearing URLs.
        code, message, retryable = "PROVIDER_CHECK_FAILED", "服务检测未能完成", False
    return {
        "name": name, "status": "failed", "code": code, "message": message,
        "retryable": retryable, "duration_ms": round((perf_counter() - started) * 1000),
    }, None


async def run_checks(settings: Settings, *, live: bool = False, provider: str = "all") -> dict:
    report = configuration_status(settings)
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    report["live_requested"] = live
    report["checks"] = []
    if not live:
        return report

    selected = [item for item in report["providers"] if provider in ("all", item["name"])]
    available = []
    for item in selected:
        if not item["configured"]:
            report["checks"].append({
                "name": item["name"], "status": "not_configured",
                "code": "PROVIDER_NOT_CONFIGURED", "missing_fields": item["missing_fields"],
            })
        else:
            available.append(item["name"])
    if not available:
        return report

    # Imports are delayed: the default command is a configuration-only operation.
    from app.providers.amap import AmapProvider
    from app.providers.llm import LlmProvider

    async with create_provider_client() as client:
        report["live_checked"] = True
        if "llm" in available:
            llm = LlmProvider(settings.llm_api_key, settings.llm_base_url, settings.llm_model, client)
            check, _ = await check_one("llm", llm.probe, lambda value: {
                "received_text": value.get("received_text", False),
                "usage": value.get("usage"),
            })
            report["checks"].append(check)
        if "amap" in available:
            amap = AmapProvider(settings.amap_web_service_key, client)
            check, poi_result = await check_one(
                "amap_poi", lambda: amap.search_pois(city="杭州", keywords="景点"),
                lambda value: {"poi_count": len(value["pois"])},
            )
            report["checks"].append(check)
            locations = []
            for poi in (poi_result or {}).get("pois", []):
                point = poi.get("location")
                if isinstance(point, str) and point and point not in locations:
                    locations.append(point)
            if len(locations) >= 2:
                check, _ = await check_one(
                    "amap_walking", lambda: amap.walking_route(locations[0], locations[1]),
                    summarize_route,
                )
            else:
                check = {"name": "amap_walking", "status": "skipped", "code": "NO_ROUTE_SAMPLE"}
            report["checks"].append(check)
            check, _ = await check_one(
                "amap_weather", lambda: amap.weather_forecast(city="330100"),
                summarize_forecasts,
            )
            report["checks"].append(check)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make real calls using configured keys")
    parser.add_argument("--provider", choices=("all", "llm", "amap"), default="all")
    parser.add_argument("--output", type=Path, help="Optional local JSON report path; contains no credentials")
    args = parser.parse_args()
    try:
        report = asyncio.run(run_checks(Settings(), live=args.live, provider=args.provider))
    except ValidationError:
        print(json.dumps({"code": "INVALID_CONFIG", "message": "请检查本地环境配置格式"}, ensure_ascii=False))
        return 2
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 2 if args.live and any(item["status"] != "succeeded" for item in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
