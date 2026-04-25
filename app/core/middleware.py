import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import clear_request_id, set_request_id

logger = logging.getLogger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, request_id_header: str = "X-Request-ID"):
        super().__init__(app)
        self.request_id_header = request_id_header

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(self.request_id_header, str(uuid.uuid4()))
        set_request_id(request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            response.headers[self.request_id_header] = request_id
            return response
        finally:
            clear_request_id()


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
