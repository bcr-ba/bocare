"""Per-request id that is attached to every log line written while handling the request."""
import contextvars
import logging
import uuid
from contextlib import contextmanager
from typing import Iterator

from fastapi import Request

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    """Attach a request ID to the logs of code running outside the request's own context
    (e.g. a streamed response, produced after the middleware has returned)."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = _request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response
