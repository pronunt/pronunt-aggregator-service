from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pronunt-service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    log_level: str = "INFO"
    log_use_colors: bool = True

    request_id_header: str = "X-Request-ID"

    auth_enabled: bool = False
    allow_unsafe_dev_auth: bool = True
    keycloak_issuer: str | None = None
    keycloak_audience: str = "pronunt-api"
    keycloak_jwks_url: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
