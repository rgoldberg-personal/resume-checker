"""GET /api/v1/jobs/{job_id}/status — poll for job status and results."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.job_store import get_job
from app.schemas import AnalysisResult, AnalysisStatus, JobStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Terminal statuses where the result field should be populated.
_RESULT_STATUSES: frozenset[str] = frozenset({"COMPLETED", "PARTIAL"})


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Poll for the current status and (when complete) results of an analysis job.

    Returns 404 if the job_id is unknown or has expired.
    """
    data: dict[str, Any] | None = get_job(job_id)

    if data is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "No job found with this ID.",
                "details": None,
            },
        )

    status_str: str = data.get("status", "RECEIVED")

    # ── Deserialise result (only for terminal success statuses) ───────────────
    result: AnalysisResult | None = None
    if status_str in _RESULT_STATUSES:
        result_raw: str = data.get("result", "")
        if result_raw:
            try:
                result = AnalysisResult.model_validate(json.loads(result_raw))
            except Exception:
                logger.warning(
                    "Could not deserialise result for job_id=%s; returning result=null.",
                    job_id,
                    exc_info=True,
                )

    # ── Deserialise warnings ──────────────────────────────────────────────────
    warnings: list[str] = []
    warnings_raw: str = data.get("warnings", "[]")
    if warnings_raw:
        try:
            warnings = json.loads(warnings_raw)
        except json.JSONDecodeError:
            warnings = []

    # ── Build response ────────────────────────────────────────────────────────
    error_message: str | None = data.get("error_message") or None

    return JobStatusResponse(
        job_id=data.get("job_id", job_id),
        status=AnalysisStatus(status_str),
        progress_step=data.get("progress_step", ""),
        created_at=data.get("created_at", ""),  # ISO string; Pydantic parses it
        result=result,
        error_message=error_message,
        warnings=warnings,
    )
