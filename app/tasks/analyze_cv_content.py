"""Task: LLM-based CV content analysis (non-critical)."""
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
from app.llm.prompts import CV_CONTENT_ANALYSIS_SYSTEM_PROMPT, build_cv_content_analysis_user_prompt
from app.schemas import CVContentAnalysis

logger = logging.getLogger(__name__)

_RETRY_SUFFIX = "\n\nReturn ONLY the JSON object, no other text."


def _call_analysis_llm(user_message: str, suffix: str = "") -> str:
    """Synchronously run the async LLM call from a Celery worker thread."""
    return asyncio.run(
        call_llm(
            system_prompt=CV_CONTENT_ANALYSIS_SYSTEM_PROMPT,
            user_content=user_message + suffix,
            response_format={"type": "json_object"},
        )
    )


@shared_task(bind=True, max_retries=1, time_limit=35)
def analyze_cv_content(self, context: dict) -> dict:  # type: ignore[override]
    """
    Analyse raw CV text with the LLM to identify content issues.

    Non-critical: on failure sets content_analysis=None and adds a warning.
    Pipeline continues regardless.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "ANALYZING_CONTENT", "Analyzing CV content...")
    start = time.time()

    try:
        raw_text: str = context.get("raw_text", "")
        user_message = build_cv_content_analysis_user_prompt(raw_text)

        # Determine prompt suffix for retry attempts
        suffix = _RETRY_SUFFIX if self.request.retries > 0 else ""

        raw_response = _call_analysis_llm(user_message, suffix)

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        try:
            analysis = CVContentAnalysis.model_validate(data)
        except ValidationError as exc:
            raise self.retry(exc=exc, countdown=2) from None

        context["content_analysis"] = analysis.model_dump()

    except Retry:
        # Let Celery handle — do NOT fall into the warning handler
        raise
    except Exception as exc:
        logger.warning("analyze_cv_content failed: %s — setting content_analysis=None", exc)
        context["content_analysis"] = None
        context["warnings"].append(f"CV content analysis unavailable: {exc!s}")

    context["step_timings"]["analyze_cv_content"] = time.time() - start
    return context
