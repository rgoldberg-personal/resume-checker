"""Strip personally identifiable information (PII) from CV text."""
from __future__ import annotations

import re

# Matches standard email addresses
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Covers CZ (+420 prefix), international (+XX), and local formats:
#   +420 123 456 789
#   +420-123-456-789
#   +420123456789
#   00420 123456789
#   123 456 789  (9-digit local)
#   (123) 456 7890  (US-style)
_PHONE_RE = re.compile(
    r"""
    (?:
        (?:\+|00)\d{1,3}[\s.\-]?   # international prefix  (+420 / 00420)
    )?
    (?:\(?\d{2,4}\)?[\s.\-]?)?     # optional area code
    \d{3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}  # 9-10 digit body
    """,
    re.VERBOSE,
)


def strip_pii_from_text(text: str) -> str:
    """
    Remove email addresses and phone numbers from text before LLM processing.

    Does not remove names (too difficult to detect reliably without NLP).
    """
    text = _EMAIL_RE.sub("[email]", text)
    text = _PHONE_RE.sub("[phone]", text)
    return text
