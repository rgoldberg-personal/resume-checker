"""Task: LLM-based CV structuring."""
from __future__ import annotations

import asyncio
import json
import time

from celery import shared_task
from celery.exceptions import Retry
from pydantic import ValidationError

from app.job_store import set_job_error, update_job_status
from app.llm.client import call_llm
from app.llm.prompts import CV_EXTRACTION_SYSTEM_PROMPT, build_extraction_user_prompt
from app.schemas import ParsedCV


def _run_llm(system_prompt: str, user_content: str, response_format: dict) -> str:
    """Run async LLM call synchronously inside a Celery worker thread."""
    return asyncio.run(
        call_llm(system_prompt, user_content, response_format)
    )


@shared_task(bind=True, max_retries=1, time_limit=35)
def extract_cv_structure(self, context: dict) -> dict:  # type: ignore[override]
    """
    Send raw CV text to GPT-4 via OpenRouter and parse into structured sections.

    Validates the LLM response with ParsedCV Pydantic model.
    Retries once if response is invalid JSON. On second failure, chain aborts.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "STRUCTURING", "Parsing CV structure with AI...")
    start = time.time()

    try:
        raw_text: str = context["raw_text"]
        user_message = build_extraction_user_prompt(raw_text)

        response = _run_llm(
            CV_EXTRACTION_SYSTEM_PROMPT,
            user_message,
            {"type": "json_object"},
        )

        try:
            parsed_cv = ParsedCV.model_validate_json(response)
        except (ValidationError, json.JSONDecodeError, ValueError) as parse_exc:
            # Retry once via Celery retry mechanism
            raise self.retry(exc=parse_exc, countdown=2) from None

        context["parsed_cv"] = parsed_cv.model_dump()

    except Retry:
        # Let Celery handle the retry — do not mark job as FAILED
        raise
    except Exception:
        set_job_error(job_id, "CV parsing failed. Please try again.")
        raise

    context["step_timings"]["extract_cv_structure"] = time.time() - start
    return context
