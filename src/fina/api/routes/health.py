"""GET / and GET /health — root redirect and liveness probe."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from fina.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root to interactive API docs."""
    return RedirectResponse(url="/docs")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return API status and version."""
    return HealthResponse(status="ok", version="0.1.0")
