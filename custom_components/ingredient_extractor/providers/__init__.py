"""AI provider registry."""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import Provider

PROVIDERS: dict[str, type[Provider]] = {AnthropicProvider.key: AnthropicProvider}


def get_provider_class(key: str) -> type[Provider]:
    """Return the provider class for a registry key (KeyError if unknown)."""
    return PROVIDERS[key]
