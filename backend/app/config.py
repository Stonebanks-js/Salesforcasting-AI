"""Application configuration via environment variables (never hardcode secrets)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # Supabase
    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: str = "dev-anon-key"
    supabase_jwt_secret: str = "dev-jwt-secret-change-me"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_enabled: bool = True

    # CORS (comma-separated origins)
    cors_origins: str = "http://localhost:3000"

    # Upload limits (mirrors api_contracts.md §2.3)
    upload_max_mb: int = 10
    upload_max_rows: int = 100_000
    upload_max_skus: int = 500

    # ASIN cap (mirrors database_design.md §A.7)
    asin_cap_per_user: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
