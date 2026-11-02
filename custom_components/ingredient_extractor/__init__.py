"""The Ingredient Extractor integration: recipe photo in, shopping list items out."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_AUTO_SORT,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_SHARE_ENABLED,
    CONF_TODO_ENTITY,
    DEFAULT_PROVIDER,
    DEFAULT_TODO_ENTITY,
    DOMAIN,
    EVENT_MOBILE_APP_SHARE,
    SERVICE_SORT_LIST,
)
from .http import IngredientExtractView
from .models import IngredientExtractorData
from .providers import get_provider_class
from .providers.base import ProviderError
from .share import async_handle_share
from .sorting import CategoryStore, async_sort_list

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

DATA_CATEGORIES: HassKey[CategoryStore] = HassKey(f"{DOMAIN}_categories")


type IngredientExtractorConfigEntry = ConfigEntry[IngredientExtractorData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the HTTP view and serve/auto-load the card (once per HA start)."""
    hass.http.register_view(IngredientExtractView())
    hass.services.async_register(
        DOMAIN,
        SERVICE_SORT_LIST,
        _async_handle_sort,
        supports_response=SupportsResponse.OPTIONAL,
    )

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


async def _async_handle_sort(call: ServiceCall) -> ServiceResponse:
    """Sort the configured todo list by shop section."""
    entries = call.hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("Ingredient Extractor is not set up")
    runtime: IngredientExtractorData = entries[0].runtime_data
    async with runtime.lock:
        try:
            moved = await async_sort_list(
                call.hass, runtime.provider, runtime.categories, runtime.todo_entity
            )
        except ProviderError as err:
            raise HomeAssistantError(str(err)) from None
    return {"moved": moved}


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
    # One store per HA run, so a reload never reads the file before a pending save.
    if (categories := hass.data.get(DATA_CATEGORIES)) is None:
        categories = hass.data[DATA_CATEGORIES] = CategoryStore(hass)
        await categories.async_load()
    entry.runtime_data = IngredientExtractorData(
        provider=provider,
        todo_entity=entry.options.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY),
        categories=categories,
        auto_sort=entry.options.get(CONF_AUTO_SORT, True),
    )

    if entry.options.get(CONF_SHARE_ENABLED, True):

        @callback
        def _on_share(event: Event) -> None:
            entry.async_create_background_task(
                hass, async_handle_share(hass, entry, event), "ingredient_extractor_share"
            )

        entry.async_on_unload(hass.bus.async_listen(EVENT_MOBILE_APP_SHARE, _on_share))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IngredientExtractorConfigEntry
) -> bool:
    """The share listener is removed by async_on_unload; the view and card stay."""
    return True
