"""Small provider boundary. No database, HTTP-route, or Jira dependencies."""

import os
from typing import Protocol


class AIProviderError(Exception):
    """Provider/configuration/output failure; never expose its raw details."""


class AIProvider(Protocol):
    def analyze(self, context: dict) -> object: ...


def create_ai_provider() -> AIProvider:
    # Resolve lazily: missing AI configuration must not disable CRUD/Jira.
    if os.environ.get("AI_PROVIDER", "gemini").strip().lower() != "gemini":
        raise AIProviderError("Unsupported AI provider.")
    from gemini_provider import GeminiProvider
    return GeminiProvider(
        model=os.environ.get("AI_MODEL", ""),
        api_key=os.environ.get("GEMINI_API_KEY", ""),
    )
