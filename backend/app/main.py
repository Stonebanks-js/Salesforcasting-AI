"""TrendCast AI FastAPI application."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.limiter import limiter
from app.routers import (calendar, forecasts, health, marketplace, products,
                         profile, signals, uploads)


def _problem(status: int, title: str, detail: str | None = None) -> dict:
    return {"type": "about:blank", "title": title, "status": status, "detail": detail}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TrendCast AI API", version=__version__)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_problem_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_problem(exc.status_code, str(exc.detail)[:80], str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_problem_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = _problem(422, "Validation failed", "Request failed schema validation")
        body["errors"] = exc.errors()
        return JSONResponse(status_code=422, content=body)

    for r in (health.router, profile.router, uploads.router, products.router,
              forecasts.router, signals.router, marketplace.router, calendar.router):
        app.include_router(r, prefix="/api/v1")

    return app


app = create_app()
