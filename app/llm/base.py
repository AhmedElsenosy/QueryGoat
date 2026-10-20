"""Abstract base class for LLM providers.

Subclass ``BaseLLMProvider`` to plug in any provider (Gemini, OpenAI,
Anthropic …).  The rest of the codebase only depends on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Minimal contract every LLM back-end must satisfy."""

    @abstractmethod
    def generate(self, prompt: str, *, system: str = "") -> str:
        """Return a single text completion.

        Args:
            prompt: The user/human message.
            system: Optional system instruction prepended to the conversation.

        Returns:
            The model's text response, stripped of leading/trailing whitespace.
        """
