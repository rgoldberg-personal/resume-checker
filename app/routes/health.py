"""GET /api/v1/health — health check endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.job_store import get_redis
from app.schemas import HealthResponse, HealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.get(
    "/health",
    response_model=HealthResponse,
    # Override status_code at runtime when Redis is down (503)
    responses={503: {"model": HealthResponse}},
)
async def health_check() -> JSONResponse:
    """
    Check backend health status.

    Returns:
      - ``"ok"``       — Redis connected; OpenRouter key configured.
      - ``"degraded"`` — Redis connected; MCP server unknown/unavailable.
      - ``"error"``    — Redis unavailable; cannot process jobs.

    Always returns HTTP 200 **except** when Redis is down (503).
    """
    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_status: str
    try:
        get_redis().ping()
        redis_status = "connected"
    except Exception:
        logger.warning("Redis health check failed.", exc_info=True)
        redis_status = "unavailable"

    # ── MCP server (stubbed as 'unknown' until the worker task is implemented) ─
    mcp_status: str = "unknown"

    # ── OpenRouter API key ────────────────────────────────────────────────────
    openrouter_status: str = (
        "configured" if settings.openrouter_api_key else "unconfigured"
    )

    # ── Overall status ────────────────────────────────────────────────────────
    if redis_status == "unavailable":
        overall = "error"
    elif mcp_status in ("unavailable", "unknown"):
        overall = "degraded"
    else:
        overall = "ok"

    body = HealthResponse(
        status=overall,
        version=settings.app_version,
        services=HealthService(
            redis=redis_status,  # type: ignore[arg-type]
            mcp_server=mcp_status,  # type: ignore[arg-type]
            openrouter=openrouter_status,  # type: ignore[arg-type]
        ),
    )

    http_status = 503 if redis_status == "unavailable" else 200
    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(),
    )
