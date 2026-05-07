"""POST /api/v1/analyze — submit a CV for analysis."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.job_store import count_active_jobs, create_job
from app.pipeline import run_analysis_pipeline
from app.schemas import AnalyzeResponse
from app.utils.file_validator import validate_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_cv(
    cv_file: UploadFile = File(..., description="PDF or DOCX CV file, max 10 MB"),  # noqa: B008
    job_description: str | None = Form(default=None, max_length=10_000),  # noqa: B008
) -> AnalyzeResponse:
    """
    Submit a CV for asynchronous analysis.

    Validates the file, saves it to disk, creates a Redis job record,
    and enqueues the Celery analysis pipeline.

    Returns a job_id to poll with GET /api/v1/jobs/{job_id}/status.
    """
    # ── Guard: file must be present ───────────────────────────────────────────
    if not cv_file or not cv_file.filename:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_FILE",
                "message": "No CV file provided.",
                "details": None,
            },
        )

    # ── Read file content (needed for size check and magic-byte validation) ───
    content: bytes = await cv_file.read()

    # ── Validate size, extension, and MIME type ───────────────────────────────
    validate_file(
        filename=cv_file.filename,
        content_type=cv_file.content_type or "",
        file_size=len(content),
        max_size=settings.max_file_size_bytes,
        file_bytes=content,
    )

    # ── Enforce concurrent job limit ──────────────────────────────────────────
    try:
        active_count = count_active_jobs()
    except Exception:
        logger.exception("Failed to count active jobs; allowing request through.")
        active_count = 0

    if active_count >= settings.max_concurrent_jobs:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "TOO_MANY_REQUESTS",
                "message": "Service busy. Please retry in a moment.",
                "details": None,
            },
        )

    # ── Generate job ID and derive file metadata ──────────────────────────────
    job_id: str = str(uuid.uuid4())
    ext: str = Path(cv_file.filename).suffix.lower()
    file_type: str = "pdf" if ext == ".pdf" else "docx"

    # ── Persist uploaded file ─────────────────────────────────────────────────
    file_path: str = os.path.join(settings.upload_dir, f"{job_id}{ext}")
    try:
        async with aiofiles.open(file_path, "wb") as fh:
            await fh.write(content)
    except OSError as exc:
        logger.exception("Failed to write uploaded file to %s", file_path)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": None,
            },
        ) from exc

    # ── Create Redis job record ───────────────────────────────────────────────
    try:
        create_job(
            job_id=job_id,
            file_type=file_type,
            job_description_provided=bool(job_description),
        )
    except Exception as exc:
        logger.exception("Failed to create job record in Redis for job_id=%s", job_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": None,
            },
        ) from exc

    # ── Enqueue Celery pipeline ───────────────────────────────────────────────
    try:
        run_analysis_pipeline(
            job_id=job_id,
            file_path=file_path,
            file_type=file_type,
            job_description=job_description,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue pipeline for job_id=%s", job_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": None,
            },
        ) from exc

    logger.info("Analysis job created: job_id=%s file_type=%s", job_id, file_type)

    return AnalyzeResponse(
        job_id=job_id,
        status="RECEIVED",
        message=(
            f"Analysis queued. Poll /api/v1/jobs/{job_id}/status for results."
        ),
    )
