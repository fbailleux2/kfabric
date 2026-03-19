from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from kfabric import __version__
from kfabric.api.routes.auth import router as auth_router
from kfabric.api.routes.mcp import router as mcp_router
from kfabric.api.routes.queries import router as queries_router
from kfabric.api.routes.system import router as system_router
from kfabric.config import get_settings
from kfabric.infra.db import init_db
from kfabric.infra.observability import REQUEST_COUNTER, REQUEST_LATENCY, get_logger, setup_logging
from kfabric.web.router import router as web_router


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id", f"tr_{uuid4().hex[:12]}")
        request.state.trace_id = trace_id
        start = perf_counter()
        response = None
        try:
            response = await call_next(request)
        finally:
            duration = perf_counter() - start
            REQUEST_COUNTER.labels(request.method, request.url.path, getattr(response, "status_code", 500)).inc()
            REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration)
        if response is not None:
            response.headers["x-trace-id"] = trace_id
            response.headers["x-content-type-options"] = "nosniff"
            response.headers["x-frame-options"] = "DENY"
            response.headers["referrer-policy"] = "no-referrer"
            response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["cross-origin-opener-policy"] = "same-origin"
            response.headers["cache-control"] = "no-store"
            if request.url.scheme == "https":
                response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
            if _is_html_response(response):
                response.headers["content-security-policy"] = (
                    "default-src 'self'; "
                    "img-src 'self' data:; "
                    "style-src 'self' 'unsafe-inline'; "
                    "script-src 'self' https://unpkg.com 'unsafe-inline'; "
                    "font-src 'self' data:; "
                    "connect-src 'self'; "
                    "frame-ancestors 'none'; "
                    "base-uri 'self'; "
                    "form-action 'self'"
                )
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    init_db(settings)
    app = FastAPI(title=settings.app_name, version=__version__, docs_url="/docs", redoc_url="/redoc")
    app.add_middleware(TraceMiddleware)
    static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(queries_router, prefix="/api/v1")
    if settings.enable_mcp:
        app.include_router(mcp_router, prefix="/api/v1")
    app.include_router(web_router)

    logger = get_logger(__name__)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", f"tr_{uuid4().hex[:12]}")
        logger.warning(
            "kfabric.http_error",
            path=str(request.url.path),
            trace_id=trace_id,
            status_code=exc.status_code,
            detail=str(exc.detail),
        )

        if exc.status_code == 401 and _is_browser_path(request.url.path):
            response = RedirectResponse(url=f"/auth?next={request.url.path}", status_code=303)
            response.headers["x-trace-id"] = trace_id
            return response

        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "error": {
                    "code": _error_code_for_status(exc.status_code),
                    "message": str(exc.detail),
                    "details": {},
                    "trace_id": trace_id,
                }
            },
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        status_code = 404 if "not found" in str(exc).lower() else 400
        logger.warning("kfabric.value_error", path=str(request.url.path), trace_id=request.state.trace_id, detail=str(exc))
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": "not_found" if status_code == 404 else "bad_request",
                    "message": str(exc),
                    "details": {},
                    "trace_id": request.state.trace_id,
                }
            },
        )

    @app.exception_handler(PermissionError)
    async def handle_permission_error(request: Request, exc: PermissionError) -> JSONResponse:
        logger.warning("kfabric.permission_error", path=str(request.url.path), trace_id=request.state.trace_id, detail=str(exc))
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "forbidden",
                    "message": str(exc),
                    "details": {},
                    "trace_id": request.state.trace_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "kfabric.validation_error",
            path=str(request.url.path),
            trace_id=request.state.trace_id,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Payload validation failed",
                    "details": {"errors": exc.errors()},
                    "trace_id": request.state.trace_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("kfabric.unexpected_error", path=str(request.url.path), trace_id=request.state.trace_id, detail=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error",
                    "details": {},
                    "trace_id": request.state.trace_id,
                }
            },
        )

    return app


app = create_app()


def _is_html_response(response) -> bool:
    media_type = response.headers.get("content-type", "").lower()
    return "text/html" in media_type


def _is_browser_path(path: str) -> bool:
    return not path.startswith("/api/")


def _error_code_for_status(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 422:
        return "validation_error"
    if 400 <= status_code < 500:
        return "bad_request"
    return "internal_error"
