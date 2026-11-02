"""Shared fixtures."""

from pathlib import Path
from unittest.mock import patch

import pytest

CATEGORIZE = "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_categorize"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load custom_components in every test."""


@pytest.fixture(autouse=True)
def categorize(request):
    """Never call the real API to classify items; everything is "Other" unless a test says so.

    Provider tests exercise the real method against a mocked SDK client instead.
    """
    if request.module.__name__.endswith("test_provider"):
        yield None
        return

    async def _other(self, names):
        return ["Other"] * len(names)

    with patch(CATEGORIZE, _other) as mock:
        yield mock


@pytest.fixture(autouse=True)
def empty_shopping_list(hass):
    """The legacy shopping list keeps its file in the shared test config dir; start empty."""
    path = Path(hass.config.path(".shopping_list.json"))
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)
