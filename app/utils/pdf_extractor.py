"""PDF text extraction using pdfplumber."""
from __future__ import annotations

import pdfplumber

_MAX_PAGES = 10


def extract_pdf_text(file_path: str) -> dict:
    """
    Extract text from a PDF file using pdfplumber.

    Reads at most the first 10 pages.  If the PDF has more pages the caller
    receives a ``truncated`` flag so a warning can be added to the job.

    Returns:
        {
            "text": str,
            "page_count": int,
            "is_image_only": bool,
            "truncated": bool,
        }
    """
    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        pages_to_read = pdf.pages[:_MAX_PAGES]

        parts: list[str] = []
        for page in pages_to_read:
            page_text = page.extract_text() or ""
            parts.append(page_text)

    text = "\n".join(parts).strip()
    is_image_only = len(text) == 0

    return {
        "text": text,
        "page_count": total_pages,
        "is_image_only": is_image_only,
        "truncated": total_pages > _MAX_PAGES,
    }
