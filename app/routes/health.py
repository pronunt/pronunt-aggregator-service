from typing import Annotated

from fastapi import APIRouter, Depends
from pymongo.errors import PyMongoError

from app.core.database import ping_database
from app.core.exceptions import AppException
from app.core.settings import Settings, get_settings

router = APIRouter(tags=["health"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _payload(status_value: str, settings: Settings) -> dict[str, str]:
    return {
        "status": status_value,
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/health")
def health(settings: SettingsDependency) -> dict[str, str]:
    return _payload("ok", settings)


@router.get("/api/v1/health")
def versioned_health(settings: SettingsDependency) -> dict[str, str]:
    return _payload("ok", settings)


@router.get("/api/v1/health/live")
def live(settings: SettingsDependency) -> dict[str, str]:
    return _payload("live", settings)


@router.get("/api/v1/health/ready")
def ready(settings: SettingsDependency) -> dict[str, str]:
    try:
        settings.validate_runtime()
        ping_database()
    except ValueError as exc:
        raise AppException(
            status_code=503,
            code="service_not_ready",
            message="Service is not ready.",
            details=str(exc),
        ) from exc
    except PyMongoError as exc:
        raise AppException(
            status_code=503,
            code="database_not_ready",
            message="Database dependency is not ready.",
            details=str(exc),
        ) from exc

    return _payload("ready", settings)
