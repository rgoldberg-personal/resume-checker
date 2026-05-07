"""MIME type, extension, and file size validation for uploaded CV files."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx"}
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Try to import python-magic at module load time; fall back gracefully.
_MAGIC_AVAILABLE = False
try:
    import magic as _magic_lib  # type: ignore[import-untyped]

    _MAGIC_AVAILABLE = True
except (ImportError, OSError):
    logger.warning(
        "libmagic is not available (install with `brew install libmagic` or "
        "`apt-get install libmagic1`). Falling back to file-extension-only "
        "validation — the MIME type reported by the client will not be verified "
        "against magic bytes."
    )


def _detect_mime_type(file_bytes: bytes) -> str | None:
    """Return the MIME type detected from magic bytes, or None if unavailable."""
    if not _MAGIC_AVAILABLE:
        return None
    try:
        return _magic_lib.from_buffer(file_bytes, mime=True)  # type: ignore[union-attr]
    except Exception:
        logger.warning("python-magic MIME detection failed; falling back to extension check.")
        return None


def validate_file(
    filename: str,
    content_type: str,
    file_size: int,
    max_size: int,
    file_bytes: bytes | None = None,
) -> None:
    """
    Validate an uploaded file for size, extension, and MIME type.

    Raises HTTPException with the correct error codes defined in api-interfaces.md §9:
      - FILE_TOO_LARGE (400) — file_size > max_size
      - INVALID_FILE_TYPE (400) — extension or MIME type not allowed

    Args:
        filename:     Original filename from the upload (used for extension check).
        content_type: MIME type reported by the HTTP client (used as fallback).
        file_size:    Total size of the file in bytes.
        max_size:     Maximum allowed size in bytes.
        file_bytes:   Raw file content. When provided and libmagic is available,
                      MIME type is verified from magic bytes rather than the
                      client-supplied content_type header.
    """
    # ── Size check ────────────────────────────────────────────────────────────
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": "File exceeds the 10 MB size limit.",
                "details": None,
            },
        )

    # ── Extension check ───────────────────────────────────────────────────────
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": "Unsupported file format. Please upload a PDF or DOCX file.",
                "details": None,
            },
        )

    # ── MIME type check ───────────────────────────────────────────────────────
    # Prefer magic-byte detection; fall back to the client-supplied content_type.
    detected_mime: str | None = None
    if file_bytes is not None:
        detected_mime = _detect_mime_type(file_bytes)

    effective_mime = detected_mime or content_type or ""

    # Only reject if we actually have a *specific* MIME type that is not in the allow-list.
    # Generic MIME types (empty or application/octet-stream) are treated as "unknown" and the
    # extension check above is considered sufficient.
    _GENERIC_MIME_TYPES = {"", "application/octet-stream"}
    if effective_mime not in _GENERIC_MIME_TYPES and effective_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": "Unsupported file format. Please upload a PDF or DOCX file.",
                "details": None,
            },
        )
