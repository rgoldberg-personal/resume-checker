"""Task: validate fields, compute confidence, store final result."""
from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from celery import shared_task
from pydantic import ValidationError

from app import job_store
from app.job_store import set_job_error, update_job_status
from app.schemas import (
    AnalysisResult,
    ATSAnalysis,
    ConfidenceLevel,
    CVContentAnalysis,
    Explanation,
    SalaryEstimate,
    ScoreBreakdown,
)

logger = logging.getLogger(__name__)


def _compute_confidence(
    raw_text: str,
    score: int,
    salary: SalaryEstimate,
    explanation: Explanation | None,
) -> ConfidenceLevel:
    """Determine the overall confidence level for the analysis result."""
    word_count = len(raw_text.split())

    if word_count < 50 or score == 0 or salary.is_low_confidence_flag:
        return ConfidenceLevel.LOW

    if explanation is None or word_count < 200:
        return ConfidenceLevel.MEDIUM

    # All sections present, explanation generated, salary in bounds
    return ConfidenceLevel.HIGH


@shared_task(bind=True, max_retries=0, time_limit=10)
def assemble_output(self, context: dict) -> dict:  # type: ignore[override]
    """
    Validate all pipeline outputs, compute confidence level, and store AnalysisResult in Redis.

    Terminal task: sets job status to COMPLETED, PARTIAL, or FAILED.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "VALIDATING", "Finalizing results...")
    start = time.time()

    try:
        # Reconstruct validated models from context dicts
        score_breakdown = ScoreBreakdown.model_validate(context["score_breakdown"])
        salary_estimate = SalaryEstimate.model_validate(context["salary_estimate"])

        # Validate numeric invariants
        if not (0 <= score_breakdown.total <= 100):
            raise ValueError(f"Invalid total score: {score_breakdown.total}")
        if not (salary_estimate.min_czk < salary_estimate.max_czk):
            raise ValueError("min_czk must be less than max_czk")
        if salary_estimate.min_czk <= 0:
            raise ValueError("min_czk must be positive")

        # Reconstruct explanation if present
        explanation_data = context.get("explanation")
        explanation: Explanation | None = None
        if explanation_data is not None:
            try:
                explanation = Explanation.model_validate(explanation_data)
            except ValidationError as exc:
                logger.warning("Explanation validation failed: %s — treating as None", exc)
                explanation = None
                context["warnings"].append("Explanation data was malformed and was dropped.")

        # Reconstruct content_analysis if present
        content_analysis_data = context.get("content_analysis")
        content_analysis: CVContentAnalysis | None = None
        if content_analysis_data is not None:
            try:
                content_analysis = CVContentAnalysis.model_validate(content_analysis_data)
            except ValidationError as exc:
                logger.warning(
                    "CVContentAnalysis validation failed: %s — treating as None", exc
                )
                content_analysis = None
                context["warnings"].append(
                    "CV content analysis data was malformed and was dropped."
                )

        # Reconstruct ats_analysis if present
        ats_analysis_data = context.get("ats_analysis")
        ats_analysis: ATSAnalysis | None = None
        if ats_analysis_data is not None:
            try:
                ats_analysis = ATSAnalysis.model_validate(ats_analysis_data)
            except ValidationError as exc:
                logger.warning("ATSAnalysis validation failed: %s — treating as None", exc)
                ats_analysis = None
                context["warnings"].append("ATS analysis data was malformed and was dropped.")

        raw_text: str = context.get("raw_text", "")
        confidence = _compute_confidence(
            raw_text, score_breakdown.total, salary_estimate, explanation
        )

        result = AnalysisResult(
            request_id=job_id,
            seniority_score=score_breakdown.total,
            score_breakdown=score_breakdown,
            salary_estimate=salary_estimate,
            explanation=explanation,
            content_analysis=content_analysis,
            ats_analysis=ats_analysis,
            confidence=confidence,
            created_at=datetime.now(UTC),
        )

        job_store.store_job_result(job_id, result.model_dump(mode="json"))

        if explanation is not None:
            final_status = "COMPLETED"
            progress_msg = "Analysis complete."
        else:
            final_status = "PARTIAL"
            progress_msg = "Analysis complete (partial results)."

        update_job_status(
            job_id,
            final_status,
            progress_msg,
            warnings=context.get("warnings", []),
        )

    except Exception as exc:
        logger.exception("assemble_output failed for job %s: %s", job_id, exc)
        set_job_error(job_id, "Failed to assemble analysis result. Please try again.")
        raise

    finally:
        # Always attempt to clean up the temp file
        file_path: str = context.get("file_path", "")
        if file_path:
            try:
                os.unlink(file_path)
            except OSError:
                pass  # File may already be gone

    context["step_timings"]["assemble_output"] = time.time() - start
    return context
