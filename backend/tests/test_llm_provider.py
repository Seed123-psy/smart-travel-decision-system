"""Protocol fixtures are synthetic; these tests never call or bill a live model."""

import asyncio
from datetime import datetime
import json

import httpx
import pytest

from app.providers.common import ProviderError
from app.providers.llm import LlmProvider


KEY = "synthetic-test-key"
BASE_URL = "https://model.example.test/custom/v1"


def completion(**overrides):
    return {
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
        **overrides,
    }


def probe_with(handler, **overrides):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True, trust_env=False,
        ) as client:
            config = {"api_key": KEY, "base_url": BASE_URL, "model": "chosen-model", **overrides}
            return await LlmProvider(**config, client=client).probe()
    return asyncio.run(run())


def test_request_preserves_prefix_and_returns_only_safe_observations():
    calls = []

    def respond(request):
        calls.append(request)
        assert str(request.url) == BASE_URL + "/chat/completions"
        assert request.headers["Authorization"] == "Bearer " + KEY
        body = json.loads(request.content)
        assert body == {
            "model": "chosen-model",
            "messages": [{"role": "user", "content": "Reply only with OK."}],
            "max_completion_tokens": 32,
            "stream": False,
        }
        assert KEY not in str(request.url)
        return httpx.Response(200, json=completion(
            choices=[{"message": {"content": "arbitrary private text", "reasoning_content": KEY}}],
            usage={"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9, "extra": KEY},
            system_fingerprint=KEY,
        ))

    result = probe_with(respond, base_url=BASE_URL + "/")
    assert len(calls) == 1
    assert set(result) == {"reachable", "received_text", "usage", "fetched_at"}
    assert result["reachable"] is True
    assert result["received_text"] is True
    assert result["usage"] == {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9}
    assert datetime.fromisoformat(result["fetched_at"]).tzinfo is not None
    assert KEY not in json.dumps(result)
    assert "private text" not in json.dumps(result)


def test_deepseek_flash_uses_documented_token_limit_and_disables_thinking():
    def respond(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert body["max_tokens"] == 32
        assert body["thinking"] == {"type": "disabled"}
        assert body["stream"] is False
        assert "max_completion_tokens" not in body
        return httpx.Response(200, json=completion())
    assert probe_with(respond, base_url="https://api.deepseek.com", model="deepseek-v4-flash")["reachable"]


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_local_http_models_are_supported(host):
    result = probe_with(
        lambda request: httpx.Response(200, json=completion(usage=None)),
        base_url=f"http://{host}:11434/v1",
    )
    assert result["usage"] is None


@pytest.mark.parametrize("field", ["api_key", "base_url", "model"])
def test_missing_configuration_makes_no_request(field):
    def forbidden(request):
        pytest.fail("Unconfigured provider must not make requests")
    with pytest.raises(ProviderError) as raised:
        probe_with(forbidden, **{field: " "})
    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"


@pytest.mark.parametrize("url", [
    "http://model.example.test/v1", "ftp://model.example.test/v1",
    "https://user:secret@model.example.test/v1", "https://@model.example.test/v1",
    "https://model.example.test/v1?key=secret", "https://model.example.test/v1?",
    "https://model.example.test/v1#secret", "https://model.example.test/v1#",
    "https://model.example.test:invalid/v1", "https://model.example.test:0/v1",
    "https://model.example.test:65536/v1", "https:///v1",
    "https://model.example.test/with space", "https://model.example.test\\secret",
    "https://model.example.test/with\nnewline",
])
def test_unsafe_addresses_are_rejected_before_io_without_echoing_config(url):
    def forbidden(request):
        pytest.fail("Invalid configuration must not make requests")
    with pytest.raises(ProviderError) as raised:
        probe_with(forbidden, base_url=url)
    assert raised.value.code == "PROVIDER_INVALID_CONFIG"
    assert "secret" not in str(raised.value)
    assert url not in str(raised.value)


@pytest.mark.parametrize("key", ["value\ninjected", "value\rinjected", "密钥"])
def test_invalid_auth_header_is_rejected_safely(key):
    def forbidden(request):
        pytest.fail("Invalid authentication header must not make requests")
    with pytest.raises(ProviderError) as raised:
        probe_with(forbidden, api_key=key)
    assert raised.value.code == "PROVIDER_INVALID_CONFIG"


@pytest.mark.parametrize("status,code,retryable", [
    (401, "PROVIDER_AUTH_FAILED", False), (403, "PROVIDER_AUTH_FAILED", False),
    (429, "PROVIDER_RATE_LIMITED", True), (500, "PROVIDER_UNAVAILABLE", True),
    (503, "PROVIDER_UNAVAILABLE", True), (400, "PROVIDER_INVALID_REQUEST", False),
    (404, "PROVIDER_INVALID_REQUEST", False), (422, "PROVIDER_INVALID_REQUEST", False),
    (302, "PROVIDER_UNAVAILABLE", False), (402, "PROVIDER_UNAVAILABLE", False),
])
def test_http_failures_are_sanitized_and_not_retried_or_redirected(status, code, retryable):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text=KEY + BASE_URL, headers={"Location": "https://other.test"})

    with pytest.raises(ProviderError) as raised:
        probe_with(respond)
    assert len(calls) == 1
    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert KEY not in str(raised.value)
    assert BASE_URL not in str(raised.value)


def test_deepseek_insufficient_balance_is_actionable_without_error_body():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(402, text=KEY)

    with pytest.raises(ProviderError) as raised:
        probe_with(respond, base_url="https://api.deepseek.com", model="deepseek-v4-flash")
    assert len(calls) == 1
    assert raised.value.code == "PROVIDER_QUOTA_EXCEEDED"
    assert raised.value.retryable is False
    assert "余额" in str(raised.value)
    assert KEY not in str(raised.value)


@pytest.mark.parametrize("error,code,retryable", [
    (httpx.ConnectTimeout, "PROVIDER_TIMEOUT", True),
    (httpx.ReadTimeout, "PROVIDER_TIMEOUT", True),
    (httpx.ConnectError, "PROVIDER_UNAVAILABLE", False),
    (httpx.RemoteProtocolError, "PROVIDER_UNAVAILABLE", False),
])
def test_transport_failures_are_sanitized_without_retries(error, code, retryable):
    calls = []

    def fail(request):
        calls.append(request)
        raise error(KEY + BASE_URL, request=request)

    with pytest.raises(ProviderError) as raised:
        probe_with(fail)
    assert len(calls) == 1
    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert KEY not in str(raised.value)
    assert BASE_URL not in str(raised.value)


@pytest.mark.parametrize("payload", [
    [], None, {}, {"choices": []}, {"choices": "wrong"}, {"choices": [None]},
    {"choices": [{"message": None}]}, {"choices": [{"message": {"content": []}}]},
    {"choices": [{"message": {"content": "  "}}]},
    {"choices": [{"message": {"content": "OK", "refusal": "private refusal"}}]},
    {"choices": [{"message": {"content": "OK"}, "finish_reason": "content_filter"}]},
    completion(usage=[]),
    completion(usage={"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2}),
    completion(usage={"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0}),
    completion(usage={"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 10}),
])
def test_empty_refused_or_malformed_response_cannot_report_success(payload):
    with pytest.raises(ProviderError) as raised:
        probe_with(lambda request: httpx.Response(200, json=payload))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert raised.value.retryable is False
    assert "private refusal" not in str(raised.value)


def test_invalid_json_cannot_report_success():
    with pytest.raises(ProviderError) as raised:
        probe_with(lambda request: httpx.Response(200, text=KEY))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert KEY not in str(raised.value)
