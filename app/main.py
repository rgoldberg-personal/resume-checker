"""FastAPI application factory with middleware, exception handlers, and startup checks."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.job_store import get_redis
from app.routes import analyze, health, jobs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup & shutdown hooks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup validation checks before accepting requests."""
    # 1. Ensure upload directory exists and is writable
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    if not os.access(upload_dir, os.W_OK):
        raise RuntimeError(
            f"Upload directory '{upload_dir}' is not writable. "
            "Run: mkdir -p {upload_dir} && chmod 755 {upload_dir}"
        )
    logger.info("Upload directory ready: %s", upload_dir)

    # 2. Verify Redis connectivity
    try:
        get_redis().ping()
        logger.info("Redis connection verified: %s", settings.redis_url)
    except Exception as exc:
        raise RuntimeError(
            f"Cannot connect to Redis at '{settings.redis_url}'. "
            "Ensure Redis is running and REDIS_URL is set correctly."
        ) from exc

    yield  # application runs here

    # (shutdown) — nothing to clean up for MVP


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(
    title="CV Analyzer API",
    description="Job Fit & Salary Estimator — CV analysis pipeline",
    version=settings.app_version,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        settings.frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": None,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": detail.get("code", "HTTP_ERROR"),
                    "message": detail.get("message", str(exc.detail)),
                    "details": detail.get("details"),
                }
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(detail),
                "details": None,
            }
        },
    )


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

app.include_router(analyze.router)
app.include_router(jobs.router)
app.include_router(health.router)
