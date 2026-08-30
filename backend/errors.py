from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from travel_assistant.model import OnlineServiceError
from travel_assistant.planner import GuideGenerationError
from travel_assistant.rag import DocumentLoadError, EmbeddingModelError

from .schemas import ErrorDetail


class AppError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details


def error_detail(exc: Exception) -> ErrorDetail:
    if isinstance(exc, AppError):
        return ErrorDetail(code=exc.code, message=str(exc), details=exc.details)
    if isinstance(exc, OnlineServiceError):
        return ErrorDetail(code=exc.code, message=str(exc), details=exc.details)
    if isinstance(exc, EmbeddingModelError):
        return ErrorDetail(code="embedding_error", message=str(exc))
    if isinstance(exc, DocumentLoadError):
        return ErrorDetail(code="document_error", message=str(exc))
    if isinstance(exc, GuideGenerationError):
        return ErrorDetail(code="guide_generation_error", message=str(exc))
    if isinstance(exc, ValueError):
        return ErrorDetail(code="invalid_value", message=str(exc))
    return ErrorDetail(code="internal_error", message="服务内部错误，请查看后端日志。")


def _status_code(exc: Exception) -> int:
    if isinstance(exc, AppError):
        return exc.status_code
    if isinstance(exc, OnlineServiceError):
        return exc.status_code
    if isinstance(exc, (DocumentLoadError, EmbeddingModelError, ValueError)):
        return 400
    if isinstance(exc, GuideGenerationError):
        return 502
    return 500


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        detail = ErrorDetail(
            code="validation_error",
            message="请求参数校验失败，请检查表单内容。",
            details=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"error": detail.model_dump()}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = ErrorDetail(
            code="http_error",
            message=str(exc.detail),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder({"error": detail.model_dump()}),
        )

    @app.exception_handler(Exception)
    async def general_handler(_request: Request, exc: Exception) -> JSONResponse:
        detail = error_detail(exc)
        return JSONResponse(
            status_code=_status_code(exc),
            content=jsonable_encoder({"error": detail.model_dump()}),
        )
