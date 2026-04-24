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
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "pronunt"
    mongodb_pr_collection: str = "aggregator_pull_requests"
    aggregator_stale_after_hours: int = 72

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
        if not self.mongodb_uri:
            errors.append("MONGODB_URI is required.")
        if not self.mongodb_database:
            errors.append("MONGODB_DATABASE is required.")
        if not self.mongodb_pr_collection:
            errors.append("MONGODB_PR_COLLECTION is required.")
        if self.aggregator_stale_after_hours <= 0:
            errors.append("AGGREGATOR_STALE_AFTER_HOURS must be greater than 0.")

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
