from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas.travel import TravelRequest

TODAY = date(2026, 9, 9)


def request_data(**overrides):
    return {
        "origin": "北京", "destination": "杭州",
        "start_date": "2026-09-10", "end_date": "2026-09-12",
        "travelers": 3, "budget_total": "6000.00", "defaults_confirmed": True,
        **overrides,
    }


def validate(**overrides):
    return TravelRequest.model_validate(request_data(**overrides), context={"today": TODAY})


def test_budget_stays_group_total_and_rooms_are_explicit():
    result = validate()
    assert result.model_dump(mode="json")["budget_total"] == "6000.00"
    assert result.currency == "CNY"
    assert result.budget_scope == "destination_only"
    assert result.rooms == 2
    assert result.daily_window.start.hour == 9


def test_single_day_same_city_has_no_hotel():
    result = validate(origin="杭州", end_date="2026-09-10")
    assert result.rooms == 0


def test_seven_days_and_ten_people_are_valid():
    assert validate(end_date="2026-09-16", travelers=10).rooms == 5


@pytest.mark.parametrize("change", [
    {"start_date": "2026-09-08"}, {"end_date": "2026-09-09"},
    {"end_date": "2026-09-17"}, {"travelers": 0}, {"travelers": 11},
    {"travelers": True}, {"travelers": 1.5}, {"budget_total": "0"},
    {"budget_total": "-1"}, {"budget_total": "10.001"},
    {"budget_total": "100000000.00"}, {"currency": "USD"},
    {"budget_scope": "entire_trip"}, {"defaults_confirmed": False},
    {"rooms": 4}, {"end_date": "2026-09-10", "rooms": 1},
    {"daily_window": {"start": "18:00", "end": "09:00"}},
    {"daily_window": {"start": "09:00+08:00", "end": "18:00+08:00"}},
    {"destination": "   "},
])
def test_rejects_invalid_business_constraints(change):
    with pytest.raises(ValidationError):
        validate(**change)


def test_http_validation_is_stateless_and_returns_safe_errors():
    # HTTP tests use future dates; domain tests above use a fixed reference clock.
    from datetime import datetime
    from app.schemas.travel import SHANGHAI

    tomorrow = datetime.now(SHANGHAI).date() + timedelta(days=1)
    payload = request_data(start_date=tomorrow.isoformat(), end_date=tomorrow.isoformat())
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        response = client.post("/api/requirements/validate", json=payload)
        assert response.status_code == 200
        assert response.json()["request"]["rooms"] == 0
        assert response.json()["valid"] is True
        assert "未保存" in response.json()["warnings"][-1]
        response = client.post("/api/requirements/validate", json={**payload, "travelers": 0})
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert response.json()["details"][0]["field"] == "travelers"
        assert "input" not in response.json()["details"][0]
        assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_liveness_does_not_claim_database_readiness():
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"
