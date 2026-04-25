import pytest

from app.core.settings import Settings


def test_runtime_validation_requires_keycloak_metadata_when_auth_is_enabled() -> None:
    settings = Settings(_env_file=None, auth_enabled=True, allow_unsafe_dev_auth=False)

    with pytest.raises(ValueError):
        settings.validate_runtime()


def test_runtime_validation_blocks_unsafe_dev_auth_in_prod() -> None:
    settings = Settings(_env_file=None, app_env="prod", allow_unsafe_dev_auth=True)

    with pytest.raises(ValueError):
        settings.validate_runtime()
