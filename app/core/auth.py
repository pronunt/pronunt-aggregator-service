from dataclasses import dataclass
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, Request, status
from jwt import InvalidTokenError, PyJWKClient

from app.core.exceptions import AppException
from app.core.request_context import get_request_id
from app.core.settings import Settings, get_settings


SettingsDependency = Annotated[Settings, Depends(get_settings)]


@dataclass
class AuthContext:
    subject: str
    username: str
    roles: list[str]
    token: str | None = None


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_authorization_header",
            message="Authorization header must use Bearer token format.",
        )
    return token


def _validate_jwt(token: str, settings: Settings) -> dict:
    if not settings.keycloak_jwks_url or not settings.keycloak_issuer:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="auth_not_configured",
            message="JWT validation is enabled but auth settings are incomplete.",
        )

    signing_key = PyJWKClient(settings.keycloak_jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.keycloak_audience,
        issuer=settings.keycloak_issuer,
    )


def _validate_pronunt_session(token: str, settings: Settings) -> AuthContext | None:
    if not settings.auth_service_url or not settings.internal_service_token:
        return None

    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            response = client.get(
                f"{settings.auth_service_url}/api/v1/auth/internal/session",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Internal-Service-Token": settings.internal_service_token,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="invalid_access_token",
                message="Access token validation failed.",
            ) from exc
        raise AppException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="auth_service_unavailable",
            message="Auth service session validation failed.",
        ) from exc
    except httpx.HTTPError as exc:
        raise AppException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="auth_service_unavailable",
            message="Auth service session validation failed.",
        ) from exc

    payload = response.json()
    return AuthContext(
        subject=payload.get("subject", payload.get("session_id", "unknown")),
        username=payload.get("username", "unknown"),
        roles=payload.get("roles", []),
        token=token,
    )


def get_auth_context(request: Request, settings: SettingsDependency) -> AuthContext:
    token = _extract_bearer_token(request)

    if not settings.auth_enabled:
        if settings.allow_unsafe_dev_auth:
            username = request.headers.get("X-Debug-User", "dev-user")
            roles = [role for role in request.headers.get("X-Debug-Roles", "developer").split(",") if role]
            return AuthContext(subject=username, username=username, roles=roles, token=token)

        if token:
            session_context = _validate_pronunt_session(token, settings)
            if session_context:
                return session_context

        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth_disabled",
            message="Authentication is disabled for this environment.",
        )

    if not token:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="missing_access_token",
            message="Access token is required.",
        )

    try:
        payload = _validate_jwt(token, settings)
    except InvalidTokenError as exc:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_access_token",
            message="Access token validation failed.",
            details=str(exc),
        ) from exc

    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    username = payload.get("preferred_username") or payload.get("sub", "unknown")

    return AuthContext(
        subject=payload.get("sub", username),
        username=username,
        roles=roles,
        token=token,
    )


def require_roles(*required_roles: str):
    auth_context_dependency = Annotated[AuthContext, Depends(get_auth_context)]

    def dependency(context: auth_context_dependency) -> AuthContext:
        if required_roles and not any(role in context.roles for role in required_roles):
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                code="insufficient_role",
                message="You do not have permission to access this resource.",
                details={"required_roles": list(required_roles)},
            )
        return context

    return dependency


def build_forward_headers(request: Request, context: AuthContext | None = None) -> dict[str, str]:
    headers = {"X-Request-ID": getattr(request.state, "request_id", get_request_id())}

    token = context.token if context else _extract_bearer_token(request)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers
