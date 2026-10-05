"""The single error shape used by every endpoint.

    {"error": {"code": "game_closed", "message": "..."}}

``code`` is stable and machine-readable; the client decides what the user sees
from it. ``message`` is for developers and never carries internal detail.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    """Raised by application code; rendered as the standard error envelope."""

    def __init__(self, code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _envelope(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_envelope(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        phrase = HTTPStatus(exc.status_code).phrase
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(phrase.lower().replace(" ", "_"), phrase),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope("invalid_request", "The request body or parameters are invalid."),
        )
