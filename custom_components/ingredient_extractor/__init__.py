"""The Ingredient Extractor integration: recipe photo in, shopping list items out."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TODO_ENTITY,
    DEFAULT_PROVIDER,
    DEFAULT_TODO_ENTITY,
    DOMAIN,
)
from .http import IngredientExtractView
from .providers import get_provider_class
from .providers.base import Provider

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class IngredientExtractorData:
    """Runtime state of a config entry."""

    provider: Provider
    todo_entity: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


type IngredientExtractorConfigEntry = ConfigEntry[IngredientExtractorData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the HTTP view and serve/auto-load the card (once per HA start)."""
    hass.http.register_view(IngredientExtractView())

    frontend_dir = Path(__file__).parent / "frontend"
    if frontend_dir.is_dir():
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(frontend_dir), cache_headers=False)]
        )
        integration = await async_get_integration(hass, DOMAIN)
        add_extra_js_url(
            hass, f"{CARD_URL_BASE}/{CARD_FILENAME}?v={integration.version}"
        )
    else:
        _LOGGER.warning("Card files not found at %s", frontend_dir)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: IngredientExtractorConfigEntry
) -> bool:
    """Build the provider from the entry."""
    provider_cls = get_provider_class(entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER))
    provider = provider_cls(
        hass,
        entry.data[CONF_API_KEY],
        entry.options.get(CONF_MODEL, provider_cls.default_model),
    )
    entry.runtime_data = IngredientExtractorData(
        provider=provider,
        todo_entity=entry.options.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY),
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IngredientExtractorConfigEntry
) -> bool:
    """Nothing to tear down; the view and card stay registered."""
    return True
