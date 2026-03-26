"""GET /health — liveness probe."""

from fastapi import APIRouter

from fina.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return API status and version."""
    return HealthResponse(status="ok", version="0.1.0")
