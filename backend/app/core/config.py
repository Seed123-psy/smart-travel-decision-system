from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "smart-travel-api"
    database_url: str = Field(default="", repr=False)
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    llm_api_key: str = Field(default="", repr=False)
    llm_base_url: str = ""
    llm_model: str = ""
    amap_web_service_key: str = Field(default="", repr=False)
    # Amadeus for Developers Self-Service uses an OAuth client pair; leave both
    # blank to keep the flight page in explicit demo mode.
    amadeus_client_id: str = Field(default="", repr=False)
    amadeus_client_secret: str = Field(default="", repr=False)
    amadeus_base_url: str = "https://test.api.amadeus.com"

    @field_validator("database_url")
    @classmethod
    def mysql_async_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith("mysql+asyncmy://"):
            raise ValueError("DATABASE_URL 必须使用 mysql+asyncmy:// 协议")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
