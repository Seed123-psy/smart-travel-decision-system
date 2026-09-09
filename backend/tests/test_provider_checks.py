import asyncio
import json

import pytest

from app.core.config import Settings
from app.providers.common import ProviderError
from app.scripts.check_providers import check_one, run_checks, summarize_forecasts, summarize_route


def empty_settings():
    return Settings(
        _env_file=None, database_url="", llm_api_key="", llm_base_url="", llm_model="",
        amap_web_service_key="",
    )


def test_missing_credentials_make_no_network_client(monkeypatch):
    def forbidden_client():
        raise AssertionError("No network client should be constructed")

    monkeypatch.setattr("app.scripts.check_providers.create_provider_client", forbidden_client)
    report = asyncio.run(run_checks(empty_settings(), live=True))
    assert report["live_checked"] is False
    assert {item["status"] for item in report["checks"]} == {"not_configured"}


def test_default_mode_never_calls_configured_services(monkeypatch):
    def forbidden_client():
        raise AssertionError("Configuration checks cannot make paid calls")

    monkeypatch.setattr("app.scripts.check_providers.create_provider_client", forbidden_client)
    settings = empty_settings().model_copy(update={
        "llm_api_key": "private-key", "llm_model": "private-model",
        "llm_base_url": "https://private-provider.example",
    })
    report = asyncio.run(run_checks(settings))
    assert report["checks"] == []
    assert report["live_checked"] is False
    assert "private-" not in json.dumps(report)


def test_probe_runner_hides_unexpected_exception_details():
    async def unsafe_operation():
        raise RuntimeError("url?key=secret-value")

    check, result = asyncio.run(check_one("example", unsafe_operation, lambda value: value))
    assert check["code"] == "PROVIDER_CHECK_FAILED"
    assert result is None
    assert "secret-value" not in json.dumps(check)


def test_probe_runner_preserves_safe_actionable_error():
    async def unavailable():
        raise ProviderError("PROVIDER_RATE_LIMITED", "调用频率超限", retryable=True)

    check, _ = asyncio.run(check_one("example", unavailable, lambda value: value))
    assert check["status"] == "failed"
    assert check["retryable"] is True


def test_empty_route_or_weather_data_cannot_pass_live_readiness():
    with pytest.raises(ProviderError, match="完整的步行"):
        summarize_route({"distance_meters": None, "duration_seconds": None})
    with pytest.raises(ProviderError, match="日期天气"):
        summarize_forecasts({"forecasts": [{"casts": []}]})
    assert summarize_route({"distance_meters": 0, "duration_seconds": 0}) == {
        "distance_meters": 0, "duration_seconds": 0,
    }
