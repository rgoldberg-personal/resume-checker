"""Redis job state read/write helpers."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis_lib.Redis | None = None  # type: ignore[type-arg]

# Statuses that mean a job is still being actively processed.
_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {"RECEIVED", "EXTRACTING", "STRUCTURING", "SCORING", "ESTIMATING", "EXPLAINING", "VALIDATING"}
)
_TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETED", "PARTIAL", "FAILED"})

# Redis hash key TTL — 2 hours
_JOB_TTL_SECONDS = 7200


def get_redis() -> redis_lib.Redis:  # type: ignore[type-arg]
    """Return a module-level singleton Redis client (lazy init)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def create_job(
    job_id: str,
    file_type: str = "",
    job_description_provided: bool = False,
) -> None:
    """
    Initialise a new job record in Redis with RECEIVED status.

    The hash key is ``job:{job_id}`` and it expires after 2 hours.
    """
    client = get_redis()
    now: str = datetime.now(UTC).isoformat()
    client.hset(
        f"job:{job_id}",
        mapping={
            "job_id": job_id,
            "status": "RECEIVED",
            "progress_step": "Uploading CV...",
            "created_at": now,
            "file_type": file_type,
            "job_description_provided": str(job_description_provided),
            "warnings": json.dumps([]),
            "result": "",
            "error_message": "",
        },
    )
    client.expire(f"job:{job_id}", _JOB_TTL_SECONDS)


def update_job_status(
    job_id: str,
    status: str,
    progress_step: str,
    warnings: list[str] | None = None,
) -> None:
    """Update the status and progress step of a job.

    Optionally replaces the warnings list when *warnings* is not None.
    """
    client = get_redis()
    mapping: dict[str, str] = {
        "status": status,
        "progress_step": progress_step,
    }
    if warnings is not None:
        mapping["warnings"] = json.dumps(warnings)
    client.hset(f"job:{job_id}", mapping=mapping)


def store_job_result(job_id: str, result: dict[str, Any]) -> None:
    """Serialise and store the final AnalysisResult dict in the job hash."""
    client = get_redis()
    client.hset(f"job:{job_id}", "result", json.dumps(result))


def set_job_error(job_id: str, error_message: str) -> None:
    """Mark a job as FAILED and store a user-facing error message."""
    client = get_redis()
    client.hset(
        f"job:{job_id}",
        mapping={
            "status": "FAILED",
            "progress_step": "Analysis failed.",
            "error_message": error_message,
        },
    )


def add_job_warning(job_id: str, warning: str) -> None:
    """Append a single warning string to the job's warnings list."""
    client = get_redis()
    raw = client.hget(f"job:{job_id}", "warnings") or "[]"
    existing: list[str] = json.loads(raw)
    existing.append(warning)
    client.hset(f"job:{job_id}", "warnings", json.dumps(existing))


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve all fields for a job hash. Returns None if the key does not exist."""
    client = get_redis()
    data: dict[str, Any] = client.hgetall(f"job:{job_id}")
    if not data:
        return None
    return data


def job_exists(job_id: str) -> bool:
    """Return True when the job key is present in Redis."""
    client = get_redis()
    return bool(client.exists(f"job:{job_id}"))


def count_active_jobs() -> int:
    """
    Count jobs whose status is not yet terminal (COMPLETED / PARTIAL / FAILED).

    Uses SCAN to iterate all ``job:*`` keys; suitable for the small number of
    concurrent jobs expected in a local/demo deployment.
    """
    client = get_redis()
    count = 0
    for key in client.scan_iter("job:*"):
        status: str | None = client.hget(key, "status")  # type: ignore[assignment]
        if status and status in _ACTIVE_STATUSES:
            count += 1
    return count
