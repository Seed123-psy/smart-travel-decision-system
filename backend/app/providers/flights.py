"""Read-only flight reference adapters (no booking).

Amap has no flight data, so flights are a separate provider. With both Amadeus
client credentials set, searches hit the real Self-Service Flight Offers API;
otherwise an explicit demo result keeps the UI usable and clearly labelled.
"""

from datetime import datetime, timedelta, timezone
import logging
import re

import httpx

from app.core.config import Settings
from app.providers.amap import _RedactQueryKeys, _install_log_filter
from app.providers.common import ProviderError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_duration(value: object) -> int:
    if not isinstance(value, str):
        return 0
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", value)
    if not match:
        return 0
    return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)


def _offer(item: dict, itinerary: dict, price: dict) -> dict:
    segments = itinerary.get("segments") if isinstance(itinerary, dict) else None
    if not isinstance(segments, list) or not segments:
        raise ProviderError("PROVIDER_INVALID_RESPONSE", "航班服务未返回可用行程，请稍后重试。")
    first = segments[0]
    last = segments[-1]
    depart = first.get("departure") if isinstance(first, dict) else None
    arrive = last.get("arrival") if isinstance(last, dict) else None
    if not isinstance(depart, dict) or not isinstance(arrive, dict):
        raise ProviderError("PROVIDER_INVALID_RESPONSE", "航班服务返回的行程数据不完整。")
    departure_at = str(depart.get("at") or "")
    arrival_at = str(arrive.get("at") or "")
    if len(departure_at) < 16 or len(arrival_at) < 16:
        raise ProviderError("PROVIDER_INVALID_RESPONSE", "航班服务返回的时间格式不正确。")
    amount = price.get("total")
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0
    return {
        "airline": str(first.get("carrierCode") or "未知航司"),
        "flight_number": f"{first.get('carrierCode') or ''}{first.get('number') or ''}",
        "depart": {"iata": depart.get("iataCode"), "time": departure_at[11:16]},
        "arrive": {"iata": arrive.get("iataCode"), "time": arrival_at[11:16]},
        "duration_minutes": _parse_duration(itinerary.get("duration")) or 0,
        "stops": max(0, len(segments) - 1),
        "price": {"amount": round(amount_value, 2), "currency": price.get("currency") or "CNY"},
    }


class FlightProvider:
    source = "amadeus"

    async def search(self, origin: str, destination: str, depart_date: str,
                     return_date: str | None, adults: int) -> dict:
        raise NotImplementedError


class AmadeusFlightProvider(FlightProvider):
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        _install_log_filter()

    async def _token(self) -> str:
        try:
            response = await self.client.post(
                self.settings.amadeus_base_url.rstrip("/") + "/v1/security/oauth2/token",
                data={"grant_type": "client_credentials",
                      "client_id": self.settings.amadeus_client_id,
                      "client_secret": self.settings.amadeus_client_secret},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "航班服务超时，请稍后重试。", True) from None
        except httpx.RequestError:
            raise ProviderError("PROVIDER_UNAVAILABLE", "无法连接航班服务，请稍后重试。", True) from None
        if response.status_code in {401, 403}:
            raise ProviderError("PROVIDER_AUTH_FAILED", "航班服务凭据无效，请检查本地配置。")
        if response.status_code >= 500:
            raise ProviderError("PROVIDER_UNAVAILABLE", "航班服务暂时不可用，请稍后重试。", True)
        payload = response.json() if response.content else {}
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ProviderError("PROVIDER_AUTH_FAILED", "航班服务鉴权失败，请检查本地配置。")
        return token

    async def search(self, origin, destination, depart_date, return_date, adults):
        token = await self._token()
        params = {
            "originLocationCode": origin, "destinationLocationCode": destination,
            "departureDate": depart_date, "adults": str(adults),
            "currencyCode": "CNY", "max": "6",
        }
        if return_date:
            params["returnDate"] = return_date
        try:
            response = await self.client.get(
                self.settings.amadeus_base_url.rstrip("/") + "/v2/shopping/flight-offers",
                params=params, headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "航班服务超时，请稍后重试。", True) from None
        except httpx.RequestError:
            raise ProviderError("PROVIDER_UNAVAILABLE", "无法连接航班服务，请稍后重试。", True) from None
        if response.status_code in {401, 403}:
            raise ProviderError("PROVIDER_AUTH_FAILED", "航班服务鉴权已失效，请刷新本地凭据后重试。")
        if response.status_code >= 500:
            raise ProviderError("PROVIDER_UNAVAILABLE", "航班服务暂时不可用，请稍后重试。", True)
        if response.status_code == 429:
            raise ProviderError("PROVIDER_RATE_LIMITED", "航班查询过于频繁，请稍后重试。", True)
        payload = response.json() if response.content else {}
        offers = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(offers, list) or not offers:
            raise ProviderError("NO_CANDIDATES", "该航线暂时没有返回可展示的航班。")
        outbound = []
        inbound = []
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            price = offer.get("price") if isinstance(offer.get("price"), dict) else {}
            itineraries = offer.get("itineraries")
            if not isinstance(itineraries, list):
                continue
            if itineraries and isinstance(itineraries[0], dict):
                try:
                    outbound.append(_offer(offer, itineraries[0], price))
                except ProviderError:
                    continue
            if len(itineraries) > 1 and isinstance(itineraries[1], dict):
                try:
                    inbound.append(_offer(offer, itineraries[1], price))
                except ProviderError:
                    continue
        if not outbound:
            raise ProviderError("PROVIDER_INVALID_RESPONSE", "航班服务返回的结果无法展示，请稍后重试。")
        now = _utcnow()
        return {
            "mode": "live", "source": "amadeus", "outbound": outbound, "inbound": inbound or None,
            "fetched_at": now.isoformat(), "expires_at": (now + timedelta(minutes=30)).isoformat(),
            "status": "ok", "summary": "已返回实时航班报价（参考），票价随库存实时变化。",
            "limitations": ["查询为参考报价，不构成预订或出票；请以航司与票务平台实时信息为准。"],
        }


class DemoFlightProvider(FlightProvider):
    """Keeps the flight page working without credentials and marks every result as demo."""

    source = "demo"

    async def search(self, origin, destination, depart_date, return_date, adults):
        now = _utcnow()
        sample = [
            {"airline": "示例航空", "flight_number": "XZ123", "stops": 0},
            {"airline": "示例航空", "flight_number": "XZ456", "stops": 1},
        ]
        offers = [
            {"airline": row["airline"], "flight_number": row["flight_number"],
             "depart": {"iata": origin, "time": "08:30" if index == 0 else "13:20"},
             "arrive": {"iata": destination, "time": "10:45" if index == 0 else "17:05"},
             "duration_minutes": 135 if index == 0 else 225, "stops": row["stops"],
             "price": {"amount": 680 + index * 340, "currency": "CNY"}}
            for index, row in enumerate(sample)
        ]
        return {
            "mode": "demo", "source": "demo", "outbound": offers, "inbound": offers if return_date else None,
            "fetched_at": now.isoformat(), "expires_at": (now + timedelta(minutes=30)).isoformat(),
            "status": "demo",
            "summary": "当前为演示数据：未配置航班服务凭据，因此返回示例航班与价格，仅供界面走通；配置后返回真实报价。",
            "limitations": ["演示数据，不构成真实航班或价格；配置 Amadeus 凭据后返回实时报价。"],
        }


def get_flight_provider(settings: Settings, client: httpx.AsyncClient) -> FlightProvider:
    if settings.amadeus_client_id.strip() and settings.amadeus_client_secret.strip():
        return AmadeusFlightProvider(settings, client)
    return DemoFlightProvider()
