from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _client():
    settings = Settings(_env_file=None, database_url="")
    return TestClient(create_app(settings))


def test_flights_search_returns_explicit_demo_without_credentials():
    with _client() as client:
        response = client.get("/api/flights/search",
                              params={"origin": "PVG", "destination": "HGH",
                                      "depart_date": "2026-10-01", "return_date": "2026-10-03", "adults": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo"
    assert body["source"] == "demo"
    assert body["origin"] == "PVG" and body["destination"] == "HGH"
    assert body["adults"] == 2
    assert body["currency"] == "CNY"
    assert len(body["outbound"]) >= 1
    assert "演示" in body["summary"]
    assert all(offer["price"]["currency"] == "CNY" for offer in body["outbound"])


def test_flights_search_returns_round_trip_inbound():
    with _client() as client:
        body = client.get("/api/flights/search",
                          params={"origin": "HGH", "destination": "SYX",
                                  "depart_date": "2026-10-01", "return_date": "2026-10-04"}).json()
    assert body["return_date"] == "2026-10-04"
    assert isinstance(body["inbound"], list) and body["inbound"]


def test_flights_search_rejects_same_city_and_bad_dates():
    with _client() as client:
        same = client.get("/api/flights/search",
                          params={"origin": "PVG", "destination": "PVG", "depart_date": "2026-10-01"})
        early = client.get("/api/flights/search",
                           params={"origin": "PVG", "destination": "HGH",
                                   "depart_date": "2026-10-05", "return_date": "2026-10-01"})
        malformed = client.get("/api/flights/search",
                               params={"origin": "PVG", "destination": "HGH", "depart_date": "10/1"})
    assert same.status_code == 422
    assert early.status_code == 422
    assert malformed.status_code == 422


def test_delete_trip_is_routed_and_reports_database_unavailability():
    # Without a configured database the delete route must answer with a clean error, not 404.
    with _client() as client:
        response = client.delete("/api/trips/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
