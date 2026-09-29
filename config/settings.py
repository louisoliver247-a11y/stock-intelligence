from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr = SecretStr("postgresql+asyncpg://stock:stock@localhost:5432/stock")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    admin_api_key: SecretStr = SecretStr("")
    token_encryption_key: SecretStr = SecretStr("")
    upstox_client_id: str = ""
    upstox_client_secret: SecretStr = SecretStr("")
    upstox_redirect_uri: str = "http://localhost:8080/api/auth/upstox/callback"
    upstox_access_token: SecretStr = SecretStr("")
    default_market_data_provider: str = "upstox"
    provider_preference: list[str] = ["upstox", "sharekhan", "hdfc_sky"]
    enable_upstox: bool = True
    enable_sharekhan: bool = False
    enable_hdfc_sky: bool = False
    sharekhan_api_key: SecretStr = SecretStr("")
    sharekhan_secret_key: SecretStr = SecretStr("")
    sharekhan_access_token: SecretStr = SecretStr("")
    web_origin: str = "http://localhost:8080"
    feed_instrument_ids: list[str] = []
    http_timeout_seconds: float = Field(20, gt=0, le=120)
    http_retries: int = Field(3, ge=0, le=6)
    history_chunk_days: int = Field(28, ge=1, le=28)
    reconcile_seconds: int = Field(60, ge=30)
    max_subscriptions: int = Field(100, ge=1, le=1500)
    max_feed_connections: int = Field(1, ge=1, le=4)
    feed_priorities: dict[str, int] = {}
    volume_baseline_period: int = Field(20, ge=5, le=200)
    abnormal_volume_multiple: float = Field(20, ge=2, le=1000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
