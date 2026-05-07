"""Task: salary estimation via live Platy.cz scraping with fallback bands."""
from __future__ import annotations

import logging
import time

from celery import shared_task

from app.job_store import update_job_status
from app.schemas import ConfidenceLevel, SalaryEstimate
from app.utils.salary_utils import (
    fallback_salary_bands,
    fetch_live_salary,
    score_to_seniority_tier,
    validate_salary_sanity,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, time_limit=15)
def estimate_salary(self, context: dict) -> dict:  # type: ignore[override]
    """
    Look up salary range from Platy MCP server. Falls back to hardcoded bands on failure.

    Non-critical degradation: failure adds warning, chain continues.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "ESTIMATING", "Looking up salary data...")
    start = time.time()

    parsed_cv: dict = context.get("parsed_cv", {})
    score_breakdown: dict = context.get("score_breakdown", {})

    # Use LLM-classified role category from CV extraction step
    role_category = parsed_cv.get("role_category", "software-engineer")
    seniority_tier = score_to_seniority_tier(score_breakdown.get("total", 0))

    min_czk: int
    max_czk: int
    data_source: str
    used_fallback = False

    live_result = fetch_live_salary(role_category, seniority_tier)
    if live_result:
        min_czk = live_result["min_czk"]
        max_czk = live_result["max_czk"]
        data_source = live_result["data_source"]
        logger.info(
            "Live Platy.cz data for %s/%s: %d–%d CZK (p10=%d, p90=%d)",
            role_category, seniority_tier, min_czk, max_czk,
            live_result["p10_czk"], live_result["p90_czk"],
        )
    else:
        logger.warning("Live salary lookup failed — using fallback bands")
        fallback = fallback_salary_bands(role_category, seniority_tier)
        min_czk = fallback["min_czk"]
        max_czk = fallback["max_czk"]
        data_source = "fallback_bands"
        used_fallback = True
        context["warnings"].append(
            "Live salary data from Platy.cz unavailable; using static fallback bands."
        )

    is_low_confidence = not validate_salary_sanity(min_czk, max_czk)

    if is_low_confidence:
        context["warnings"].append(
            f"Salary estimate ({min_czk:,}–{max_czk:,} CZK) is outside expected bounds."
        )

    # Build confidence: low if fallback + low confidence, otherwise medium by default
    # (assemble_output can upgrade to high)
    if used_fallback and is_low_confidence:
        salary_confidence = ConfidenceLevel.LOW
    else:
        salary_confidence = ConfidenceLevel.MEDIUM

    salary_estimate = SalaryEstimate(
        min_czk=min_czk,
        max_czk=max_czk,
        data_source=data_source,
        confidence=salary_confidence,
        is_low_confidence_flag=is_low_confidence,
    )
    context["salary_estimate"] = salary_estimate.model_dump()
    context["role_category"] = role_category
    context["seniority_tier"] = seniority_tier

    context["step_timings"]["estimate_salary"] = time.time() - start
    return context
