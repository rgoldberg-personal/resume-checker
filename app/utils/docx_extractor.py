"""DOCX text extraction using python-docx."""
from __future__ import annotations

import docx


def extract_docx_text(file_path: str) -> dict:
    """
    Extract text from a DOCX file using python-docx.

    Returns:
        {
            "text": str,
            "paragraph_count": int,
        }
    """
    document = docx.Document(file_path)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs).strip()

    return {
        "text": text,
        "paragraph_count": len(paragraphs),
    }
