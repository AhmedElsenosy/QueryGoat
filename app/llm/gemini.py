"""Google Gemini LLM provider using the google-genai SDK."""

from __future__ import annotations

from google import genai
from google.genai import types

from .base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Wraps the ``google-genai`` SDK behind :class:`BaseLLMProvider`."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    def generate(self, prompt: str, *, system: str = "") -> str:
        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        text = response.text
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()
