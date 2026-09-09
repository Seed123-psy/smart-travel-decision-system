"""Bounded async Chat Completions calls without raw-response logging."""

from datetime import datetime, timezone
import json
from urllib.parse import urlsplit

import httpx

from app.providers.common import ProviderError


class LlmProvider:
    def __init__(self, api_key: str, base_url: str, model: str, client: httpx.AsyncClient):
        self._api_key = api_key.strip()
        self._base_url = base_url.strip()
        self._model = model.strip()
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        # HelloAgents uses this label in its safe Agent representation.
        return "chat-completions"

    def _endpoint(self) -> str:
        if not all((self._api_key, self._base_url, self._model)):
            raise ProviderError("PROVIDER_NOT_CONFIGURED", "请先配置模型服务地址、模型名称和密钥。")
        try:
            parts = urlsplit(self._base_url)
            valid_scheme = parts.scheme == "https" or (
                parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}
            )
            valid = (
                valid_scheme
                and bool(parts.hostname)
                and parts.username is None
                and parts.password is None
                and not any(char in self._base_url for char in "?#\\")
                and not any(char.isspace() or ord(char) < 32 for char in self._base_url)
                and (parts.port is None or 1 <= parts.port <= 65535)
                and all(32 < ord(char) < 127 for char in self._api_key)
            )
            if not valid:
                raise ValueError
            # A provider may use /v1 or a custom prefix; never discard that path.
            return str(httpx.URL(self._base_url.rstrip("/") + "/chat/completions"))
        except (ValueError, httpx.InvalidURL):
            raise ProviderError("PROVIDER_INVALID_CONFIG", "模型服务配置无效，请检查地址和密钥格式。") from None

    async def probe(self) -> dict:
        _, usage = await self._complete(
            [{"role": "user", "content": "Reply only with OK."}], max_tokens=32,
        )
        return {
            "reachable": True,
            "received_text": True,
            "usage": usage,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def generate_json(self, messages: list[dict], *, max_tokens: int = 1024) -> tuple[dict, dict | None]:
        if not 1 <= max_tokens <= 4096 or len(json.dumps(messages, ensure_ascii=False)) > 60_000:
            raise ProviderError("PROVIDER_INVALID_REQUEST", "模型请求超过当前规划的大小限制。")
        content, usage = await self._complete(messages, max_tokens=max_tokens, json_mode=True)
        try:
            value = json.loads(content)
        except (ValueError, RecursionError):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型未生成有效 JSON，请重新规划。") from None
        if not isinstance(value, dict):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型未生成有效 JSON 对象，请重新规划。")
        return value, usage

    async def _complete(
        self, messages: list[dict], *, max_tokens: int, json_mode: bool = False,
    ) -> tuple[str, dict | None]:
        endpoint = self._endpoint()
        request_body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if httpx.URL(endpoint).host == "api.deepseek.com":
            # DeepSeek's documented Chat API uses max_tokens and enables thinking by default.
            request_body.update(max_tokens=max_tokens, thinking={"type": "disabled"})
        else:
            request_body["max_completion_tokens"] = max_tokens
        if json_mode:
            request_body["response_format"] = {"type": "json_object"}
        try:
            response = await self._client.post(
                endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request_body,
                follow_redirects=False,
                timeout=httpx.Timeout(20.0, connect=5.0),
            )
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "模型服务请求超时，请稍后手动重试。", True) from None
        except httpx.RequestError:
            raise ProviderError("PROVIDER_UNAVAILABLE", "暂时无法连接模型服务，请检查服务配置。") from None
        except (ValueError, UnicodeError):
            raise ProviderError("PROVIDER_INVALID_CONFIG", "模型服务配置无效，请检查地址和密钥格式。") from None

        if response.status_code in {401, 403}:
            raise ProviderError("PROVIDER_AUTH_FAILED", "模型服务鉴权失败，请检查密钥和访问权限。")
        if response.status_code == 402 and httpx.URL(endpoint).host == "api.deepseek.com":
            raise ProviderError("PROVIDER_QUOTA_EXCEEDED", "DeepSeek 账户余额不足，请在服务商控制台检查余额。")
        if response.status_code in {400, 404, 422}:
            raise ProviderError("PROVIDER_INVALID_REQUEST", "模型服务请求无效，请检查服务地址、模型名称和参数。")
        if response.status_code == 429:
            raise ProviderError("PROVIDER_RATE_LIMITED", "模型服务请求受限，请检查额度或稍后手动重试。", True)
        if not 200 <= response.status_code < 300:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE", "模型服务未成功响应，请检查地址、模型与服务状态。",
                response.status_code >= 500,
            )

        if len(response.content) > 200_000:
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型返回的数据超过大小限制。")
        try:
            payload = response.json()
        except (ValueError, UnicodeError, RecursionError):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务返回了无法识别的数据。") from None
        if not isinstance(payload, dict):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务返回了无法识别的数据。")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务未返回有效文本。")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务未返回有效文本。")
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务拒绝了请求。")
        if json_mode and choice.get("finish_reason") == "length":
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型输出达到上限，未取得完整结构化结果。")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务未返回有效文本。")

        usage = self._safe_usage(payload.get("usage"))
        return content, usage

    @staticmethod
    def _safe_usage(raw: object) -> dict[str, int] | None:
        if raw is None:
            return None
        fields = ("prompt_tokens", "completion_tokens", "total_tokens")
        if not isinstance(raw, dict) or any(
            type(raw.get(field)) is not int or raw[field] < 0 for field in fields
        ):
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务返回的用量数据无效。")
        if raw["total_tokens"] != raw["prompt_tokens"] + raw["completion_tokens"]:
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "模型服务返回的用量数据无效。")
        return {field: raw[field] for field in fields}
