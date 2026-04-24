import asyncio
import logging
from typing import Any

import httpx
from fastapi import Request, status

from app.core.auth import AuthContext, build_forward_headers
from app.core.exceptions import AppException
from app.core.settings import get_settings

logger = logging.getLogger("app.http")


async def service_request(
    method: str,
    url: str,
    *,
    request: Request | None = None,
    auth_context: AuthContext | None = None,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    settings = get_settings()
    outbound_headers: dict[str, str] = {}

    if request is not None:
        outbound_headers.update(build_forward_headers(request, auth_context))

    if headers:
        outbound_headers.update(headers)

    try:
        async with httpx.AsyncClient() as client:
            async with asyncio.timeout(settings.http_timeout_seconds):
                response = await client.request(method, url, headers=outbound_headers, **kwargs)
                response.raise_for_status()
                return response
    except httpx.TimeoutException as exc:
        raise AppException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="upstream_timeout",
            message="Upstream service request timed out.",
            details={"url": url, "method": method},
        ) from exc
    except TimeoutError as exc:
        raise AppException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="upstream_timeout",
            message="Upstream service request timed out.",
            details={"url": url, "method": method},
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "upstream service returned error",
            extra={
                "method": method,
                "path": url,
                "status_code": exc.response.status_code,
            },
        )
        raise AppException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="upstream_http_error",
            message="Upstream service request failed.",
            details={
                "url": url,
                "method": method,
                "upstream_status": exc.response.status_code,
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise AppException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="upstream_unavailable",
            message="Upstream service is unavailable.",
            details={"url": url, "method": method},
        ) from exc
