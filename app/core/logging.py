import logging
import sys
from datetime import datetime, timezone

from app.core.request_context import get_request_id


_RESET = "\033[0m"
_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}


class RequestContextFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.service = self.service_name
        return True


class StructuredFormatter(logging.Formatter):
    def __init__(self, use_colors: bool = False) -> None:
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        level = record.levelname
        if self.use_colors:
            level = f"{_COLORS.get(record.levelname, '')}{record.levelname}{_RESET}"

        fields = [
            f"timestamp={timestamp}",
            f"level={record.levelname}",
            f"service={getattr(record, 'service', '-')}",
            f"logger={record.name}",
            f"request_id={getattr(record, 'request_id', '-')}",
            f'message="{record.getMessage()}"',
        ]

        for attr in ("method", "path", "status_code", "duration_ms"):
            value = getattr(record, attr, None)
            if value is not None:
                fields.append(f"{attr}={value}")

        line = " ".join(fields)
        if self.use_colors:
            return f"{level} {line}"
        return line


def configure_logging(service_name: str, log_level: str, use_colors: bool) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(use_colors=use_colors and sys.stdout.isatty()))
    handler.addFilter(RequestContextFilter(service_name=service_name))

    root_logger.addHandler(handler)
