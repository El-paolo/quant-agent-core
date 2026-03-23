"""
FastAPI application factory for FINA.

Always use create_app() — never import `app` directly in tests.
The factory pattern allows injecting a custom Settings object,
making the app fully testable without touching env variables.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fina.api.middleware import RequestTimingMiddleware
from fina.core.config import Settings, get_settings
from fina.core.exceptions import ConfigError


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Create and configure the FINA FastAPI application.

    Args:
        settings: Optional Settings override. If None, settings are loaded
                  from the environment/.env file. Pass a custom Settings
                  instance in tests to avoid touching env variables.

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    # --- Configure caches with settings values ---
    from fina.data.fetcher import configure_price_cache
    from fina.agent.news import configure_news_cache

    configure_price_cache(
        ttl=settings.cache_prices_ttl_seconds,
        maxsize=settings.cache_max_size,
    )
    configure_news_cache(
        ttl=settings.cache_news_ttl_seconds,
        maxsize=settings.cache_max_size,
    )

    app = FastAPI(
        title="FINA Financial Analysis API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- Exception handlers ---
    @app.exception_handler(ConfigError)
    async def config_error_handler(request: Request, exc: ConfigError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    # --- Middleware (order matters: last added = outermost) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestTimingMiddleware)

    # --- Routes (imported inside factory to avoid circular imports) ---
    from fina.api.routes.health import router as health_router
    from fina.api.routes.analysis import router as analysis_router
    from fina.api.routes.agent import router as agent_router

    app.include_router(health_router)
    app.include_router(analysis_router, prefix="/analysis")
    app.include_router(agent_router, prefix="/agent")

    return app


# Module-level app instance for uvicorn: `uvicorn fina.api.main:app --reload`
app = create_app()
