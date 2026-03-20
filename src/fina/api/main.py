"""
FastAPI application factory for FINA.

Always use create_app() — never import `app` directly in tests.
The factory pattern allows injecting a custom Settings object,
making the app fully testable without touching env variables.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fina.api.middleware import RequestTimingMiddleware
from fina.core.config import Settings, get_settings


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

    app = FastAPI(
        title="FINA Financial Analysis API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

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

    app.include_router(health_router)
    app.include_router(analysis_router, prefix="/analysis")

    return app


# Module-level app instance for uvicorn: `uvicorn fina.api.main:app --reload`
app = create_app()
