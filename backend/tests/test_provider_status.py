from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_status_reveals_missing_names_but_never_credentials_or_connection_urls():
    settings = Settings(
        _env_file=None, database_url="", llm_api_key="private-model-token",
        llm_base_url="https://private-provider.example/v1", llm_model="private-model",
        amap_web_service_key="private-map-token",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/providers/status")
    assert response.status_code == 200
    assert response.json()["live_checked"] is False
    assert {item["status"] for item in response.json()["providers"]} == {"not_verified"}
    assert all(item["configured"] for item in response.json()["providers"])
    assert "private-" not in response.text


def test_partial_and_whitespace_configuration_remain_not_configured():
    settings = Settings(
        _env_file=None, database_url="", llm_api_key="present", llm_model="  ",
        llm_base_url="", amap_web_service_key="  ",
    )
    with TestClient(create_app(settings)) as client:
        result = client.get("/api/providers/status").json()
    assert result["providers"][0]["missing_fields"] == ["LLM_BASE_URL", "LLM_MODEL"]
    assert result["providers"][1]["missing_fields"] == ["AMAP_WEB_SERVICE_KEY"]
    assert all(item["status"] == "not_configured" for item in result["providers"])
