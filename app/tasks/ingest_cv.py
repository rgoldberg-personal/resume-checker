"""Task: validate file, extract raw text, strip PII."""
from __future__ import annotations

import os
import time

from celery import shared_task

from app.job_store import set_job_error, update_job_status
from app.utils.docx_extractor import extract_docx_text
from app.utils.pdf_extractor import extract_pdf_text
from app.utils.pii_stripper import strip_pii_from_text


@shared_task(bind=True, max_retries=0, time_limit=15)
def ingest_cv(self, context: dict) -> dict:  # type: ignore[override]
    """
    Validate the uploaded file, extract raw text (PDF/DOCX), and strip PII.

    Sets job status to EXTRACTING before processing.
    Raises on empty text or invalid file — chain aborts, job → FAILED.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "EXTRACTING", "Extracting text from document...")
    start = time.time()

    try:
        file_path: str = context["file_path"]
        file_type: str = context.get("file_type", "").lower()

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded file not found: {file_path}")

        if file_type == "pdf":
            result = extract_pdf_text(file_path)
            text: str = result["text"]

            if result.get("is_image_only"):
                raise ValueError(
                    "No text found in the PDF. "
                    "Please provide a text-based (not scanned) PDF."
                )

            if result.get("truncated"):
                warning = (
                    f"PDF has {result['page_count']} pages; "
                    "only the first 10 pages were analysed."
                )
                context["warnings"].append(warning)

        elif file_type in ("docx", "doc"):
            result = extract_docx_text(file_path)
            text = result["text"]
        else:
            raise ValueError(f"Unsupported file type: {file_type!r}")

        word_count = len(text.split())
        if word_count < 50:
            raise ValueError(
                "Insufficient text. Please provide a more complete CV."
            )

        text = strip_pii_from_text(text)
        context["raw_text"] = text

    except Exception as exc:
        set_job_error(job_id, str(exc))
        raise

    context["step_timings"]["ingest_cv"] = time.time() - start
    return context
