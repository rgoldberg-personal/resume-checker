"""Async httpx wrapper for OpenRouter LLM calls."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMTimeoutError(Exception):
    """Raised when the LLM call exceeds the configured timeout."""


class LLMAPIError(Exception):
    """Raised when the LLM API returns a non-2xx response or unexpected payload."""


async def call_llm(
    system_prompt: str,
    user_content: str,
    response_format: dict | None = None,
) -> str:
    """
    Send a chat completion request to OpenRouter.

    Returns the content string from the first choice.
    Raises LLMTimeoutError on timeout, LLMAPIError on non-2xx or unexpected payload.
    """
    payload: dict = {
        "model": settings.openrouter_model,
        "temperature": settings.llm_temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if response_format is not None:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        msg = f"LLM request timed out after {settings.llm_timeout_seconds}s"
        raise LLMTimeoutError(msg) from exc

    if response.status_code != 200:
        raise LLMAPIError(
            f"OpenRouter returned HTTP {response.status_code}: {response.text[:200]}"
        )

    try:
        data = response.json()
        content: str = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMAPIError(f"Unexpected response structure from OpenRouter: {exc}") from exc

    return content


async def call_llm_with_retry(
    system_prompt: str,
    user_content: str,
    response_format: dict | None = None,
    max_retries: int = 1,
) -> str:
    """
    Call the LLM with automatic retry on transient failure.

    On each retry, appends a reminder to return only the JSON object.
    Raises the last exception after all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await call_llm(system_prompt, user_content, response_format)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, exc)
            if attempt < max_retries:
                user_content = user_content + "\n\nReturn ONLY the JSON object, no other text."

    raise last_exc  # type: ignore[misc]
