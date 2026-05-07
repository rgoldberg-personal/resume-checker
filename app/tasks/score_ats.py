"""Task: ATS scoring against a job description (non-critical)."""
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
from app.llm.prompts import ATS_SCORING_SYSTEM_PROMPT, build_ats_scoring_user_prompt
from app.schemas import ATSAnalysis

logger = logging.getLogger(__name__)

_RETRY_SUFFIX = "\n\nReturn ONLY the JSON object, no other text."


def _call_ats_llm(user_message: str, suffix: str = "") -> str:
    """Synchronously run the async LLM call from a Celery worker thread."""
    return asyncio.run(
        call_llm(
            system_prompt=ATS_SCORING_SYSTEM_PROMPT,
            user_content=user_message + suffix,
            response_format={"type": "json_object"},
        )
    )


@shared_task(bind=True, max_retries=1, time_limit=60)
def score_ats(self, context: dict) -> dict:  # type: ignore[override]
    """
    Score the CV against the provided job description using ATS criteria.

    Skip logic: if no job_description is present, sets ats_analysis=None immediately
    without an LLM call or warning — this is expected behaviour.

    Non-critical: on LLM failure sets ats_analysis=None and appends a warning.
    Pipeline continues regardless.
    """
    start = time.time()

    # Skip gracefully when no job description was provided
    if not context.get("job_description"):
        context["ats_analysis"] = None
        context["step_timings"]["score_ats"] = time.time() - start
        return context

    job_id = context["job_id"]
    update_job_status(job_id, "ATS_SCORING", "Scoring against job description...")

    try:
        raw_text: str = context.get("raw_text", "")
        job_description: str = context["job_description"]

        user_message = build_ats_scoring_user_prompt(raw_text, job_description)

        # Determine prompt suffix for retry attempts
        suffix = _RETRY_SUFFIX if self.request.retries > 0 else ""

        raw_response = _call_ats_llm(user_message, suffix)

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        try:
            ats = ATSAnalysis.model_validate(data)
        except ValidationError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        context["ats_analysis"] = ats.model_dump()

    except Retry:
        # Let Celery handle — do NOT fall into the warning handler
        raise
    except Exception as exc:
        logger.warning("score_ats failed: %s — setting ats_analysis=None", exc)
        context["ats_analysis"] = None
        context["warnings"].append(f"ATS scoring unavailable: {exc!s}")

    context["step_timings"]["score_ats"] = time.time() - start
    return context
