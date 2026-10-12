import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging_context import get_request_id

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The orchestrator already turns pipeline failures into a user-facing reply,
        # so reaching this handler means a bug in the API layer itself.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error.",
                               "request_id": get_request_id()}},
        )
