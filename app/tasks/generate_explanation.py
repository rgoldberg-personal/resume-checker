"""Task: LLM-generated explanation (non-critical)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from celery import shared_task
from celery.exceptions import Retry
from pydantic import ValidationError

from app.job_store import update_job_status
from app.llm.client import call_llm
from app.llm.prompts import EXPLANATION_SYSTEM_PROMPT, build_explanation_user_prompt
from app.schemas import Explanation
from app.utils.pii_stripper import strip_pii_from_text

logger = logging.getLogger(__name__)

_RETRY_SUFFIX = "\n\nReturn ONLY the JSON object, no other text."


def _call_explanation_llm(user_message: str, suffix: str = "") -> str:
    """Synchronously run the async LLM call from a Celery worker thread."""
    return asyncio.run(
        call_llm(
            system_prompt=EXPLANATION_SYSTEM_PROMPT,
            user_content=user_message + suffix,
            response_format={"type": "json_object"},
        )
    )


@shared_task(bind=True, max_retries=1, time_limit=35)
def generate_explanation(self, context: dict) -> dict:  # type: ignore[override]
    """
    Generate a natural-language explanation via GPT-4.

    Non-critical: on failure sets explanation=None and adds a warning.
    Pipeline continues with PARTIAL result.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "EXPLAINING", "Generating explanation...")
    start = time.time()

    try:
        parsed_cv: dict = context.get("parsed_cv", {})
        score_breakdown: dict = context.get("score_breakdown", {})
        salary_estimate: dict = context.get("salary_estimate", {})
        job_description: str | None = context.get("job_description")

        # Build a safe CV summary (PII stripped)
        sections = parsed_cv.get("sections", {})
        cv_summary: dict = {
            "experience_years": parsed_cv.get("experience_years", 0),
            "skills": parsed_cv.get("skills", []),
            "soft_skills": parsed_cv.get("soft_skills", []),
            "education_level": parsed_cv.get("education_level", "unknown"),
            "certifications": sections.get("certifications", ""),
            "role_titles": parsed_cv.get("role_titles", []),
            "has_management_indicators": parsed_cv.get("has_management_indicators", False),
            "role_category": parsed_cv.get("role_category", ""),
        }
        if job_description:
            cv_summary["job_description_snippet"] = strip_pii_from_text(job_description[:500])

        user_message = build_explanation_user_prompt(
            seniority_score=score_breakdown.get("total", 0),
            score_breakdown=score_breakdown,
            salary_estimate=salary_estimate,
            parsed_cv_summary=cv_summary,
        )

        # Determine prompt suffix for retry attempts
        suffix = _RETRY_SUFFIX if self.request.retries > 0 else ""

        raw_response = _call_explanation_llm(user_message, suffix)

        # The LLM returns summary/strengths/weaknesses/recommendations.
        # raw_llm_response is stored for debugging but not expected from LLM.
        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        data["raw_llm_response"] = raw_response

        try:
            explanation = Explanation.model_validate(data)
        except ValidationError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        context["explanation"] = explanation.model_dump()

    except Retry:
        # Let Celery handle — do NOT fall into the warning handler
        raise
    except Exception as exc:
        logger.warning("generate_explanation failed: %s — setting explanation=None", exc)
        context["explanation"] = None
        context["warnings"].append(f"LLM explanation unavailable: {exc!s}")

    context["step_timings"]["generate_explanation"] = time.time() - start
    return context
