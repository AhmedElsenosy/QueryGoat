"""LLM provider abstraction layer.

Usage::

    from app.llm import get_llm_provider

    llm = get_llm_provider()
    answer = llm.generate("Rewrite this …", system="You are …")

To add a new provider, create a file in this package (e.g. ``openai.py``),
subclass :class:`BaseLLMProvider`, and register it in :func:`get_llm_provider`.
"""

from __future__ import annotations

from .base import BaseLLMProvider
from .gemini import GeminiProvider


def get_llm_provider() -> BaseLLMProvider:
    """Return the configured LLM provider based on env vars.

    Raises:
        RuntimeError: If no provider API key is set.
    """
    from app.config import settings

    if settings.gemini_api_key:
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
    raise RuntimeError(
        "No LLM provider configured. Set GEMINI_API_KEY in .env."
    )


__all__ = ["BaseLLMProvider", "GeminiProvider", "get_llm_provider"]
