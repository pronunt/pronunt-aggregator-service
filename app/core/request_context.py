from contextvars import ContextVar


_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id_context.set(request_id)


def get_request_id() -> str:
    return _request_id_context.get()


def clear_request_id() -> None:
    _request_id_context.set("-")
