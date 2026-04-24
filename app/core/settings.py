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
    http_timeout_seconds: float = 10.0

    auth_enabled: bool = False
    allow_unsafe_dev_auth: bool = True
    keycloak_issuer: str | None = None
    keycloak_audience: str = "pronunt-api"
    keycloak_jwks_url: str | None = None

    def validate_runtime(self) -> None:
        errors: list[str] = []
        secure_envs = {"test", "testing", "stage", "staging", "prod", "production"}

        if self.http_timeout_seconds <= 0:
            errors.append("HTTP_TIMEOUT_SECONDS must be greater than 0.")

        if self.auth_enabled:
            if not self.keycloak_issuer:
                errors.append("KEYCLOAK_ISSUER is required when AUTH_ENABLED=true.")
            if not self.keycloak_jwks_url:
                errors.append("KEYCLOAK_JWKS_URL is required when AUTH_ENABLED=true.")

        if self.app_env.lower() in secure_envs and self.allow_unsafe_dev_auth:
            errors.append("ALLOW_UNSAFE_DEV_AUTH must be false outside local development.")

        if errors:
            raise ValueError(" ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
