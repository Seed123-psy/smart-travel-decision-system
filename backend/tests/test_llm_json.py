"""Synthetic JSON protocol fixtures; no real model requests."""

import asyncio
import json

import httpx
import pytest

from app.providers.common import ProviderError
from app.providers.llm import LlmProvider


MESSAGES = [{"role": "system", "content": "Return a JSON object without reasoning."},
            {"role": "user", "content": "Synthetic test only."}]


def generate(handler, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            provider = LlmProvider("synthetic-key", "https://api.deepseek.com", "deepseek-v4-flash", client)
            return await provider.generate_json(kwargs.pop("messages", MESSAGES), **kwargs)
    return asyncio.run(run())


def response(content, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content,
            "reasoning_content": "private synthetic reasoning"}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 4, "total_tokens": 19}})


def test_json_generation_keeps_user_model_and_actual_usage_with_bounded_output(capsys):
    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert body["max_tokens"] == 3500
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"] == MESSAGES
        assert body["stream"] is False
        return response('{"selected":"POI1"}')
    value, usage = generate(handle, max_tokens=3500)
    assert value == {"selected": "POI1"}
    assert usage["total_tokens"] == 19
    assert not capsys.readouterr().out


@pytest.mark.parametrize("content,finish", [
    ("private raw response", "stop"), ("[]", "stop"), ("null", "stop"),
    ('{"selected":"POI1"}', "length"), ('```json\n{"value":1}\n```', "stop"),
])
def test_malformed_or_incomplete_json_is_rejected_without_exposing_content(content, finish):
    with pytest.raises(ProviderError) as raised:
        generate(lambda request: response(content, finish))
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert "private raw response" not in str(raised.value)


@pytest.mark.parametrize("limit", [0, 4097])
def test_request_output_limits_prevent_model_call(limit):
    def forbidden(request):
        pytest.fail("Invalid request limits must not call a model")
    with pytest.raises(ProviderError) as raised:
        generate(forbidden, max_tokens=limit)
    assert raised.value.code == "PROVIDER_INVALID_REQUEST"


def test_oversized_model_input_is_rejected_before_network_io():
    def forbidden(request):
        pytest.fail("Oversized input must not call a model")
    with pytest.raises(ProviderError) as raised:
        generate(forbidden, messages=[{"role": "user", "content": "x" * 60_000}])
    assert raised.value.code == "PROVIDER_INVALID_REQUEST"


def test_json_http_request_cancellation_is_not_retried_or_translated():
    async def run():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def pending(request):
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise
        async with httpx.AsyncClient(transport=httpx.MockTransport(pending)) as client:
            model = LlmProvider("synthetic-key", "https://api.deepseek.com", "deepseek-v4-flash", client)
            task = asyncio.create_task(model.generate_json(MESSAGES))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set()
    asyncio.run(run())
