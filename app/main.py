from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import AccessLogMiddleware, RequestContextMiddleware
from app.core.settings import get_settings
from app.routes.health import router as health_router
from app.routes.v1 import router as v1_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        service_name=settings.app_name,
        log_level=settings.log_level,
        use_colors=settings.log_use_colors,
    )

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware, request_id_header=settings.request_id_header)
    app.add_middleware(AccessLogMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(v1_router, prefix="/api/v1/aggregator")
    return app


app = create_app()
