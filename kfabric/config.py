from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KFABRIC_", env_file=".env", extra="ignore")

    app_name: str = "KFabric"
    env: str = "development"
    database_url: str = "sqlite:///./kfabric.db"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"
    qdrant_url: str = "http://localhost:6333"
    storage_path: Path = Field(default=Path("./storage"))
    api_key: str | None = None
    enable_metrics: bool = True
    enable_mcp: bool = True
    secure_mode: bool = True
    remote_discovery_enabled: bool = False
    remote_collection_enabled: bool = False
    max_fragment_chars: int = 280
    accept_threshold: int = 75
    salvage_threshold: int = 45
    session_ttl_seconds: int = 3600

    def ensure_storage(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_storage()
    return settings
