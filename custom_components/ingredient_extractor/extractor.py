"""Orchestrates one extraction: provider call, formatting, adding to the todo list."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import EXTRACT_TIMEOUT_SECONDS
from .fetch import async_fetch_recipe
from .formatting import format_item
from .providers.base import Extraction, Provider, ProviderTimeoutError

_LOGGER = logging.getLogger(__name__)


class NotARecipeError(Exception):
    """The image or page does not show a recipe."""


class NoIngredientsError(Exception):
    """A recipe was recognised but no ingredients could be read."""


class TodoAddError(Exception):
    """Adding to the todo list failed part-way."""

    def __init__(self, added: list[str]) -> None:
        """Keep the items that were added before the failure."""
        super().__init__("Could not add items to the todo list")
        self.added = added


async def _async_add_extraction(
    hass: HomeAssistant,
    todo_entity: str,
    extraction: Extraction,
) -> list[str]:
    """Format an extraction and add each item to the todo entity."""
    if not extraction.is_recipe:
        raise NotARecipeError
    items = [s for s in map(format_item, extraction.ingredients) if s]
    if not items:
        raise NoIngredientsError

    added: list[str] = []
    for item in items:
        try:
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": item},
                target={"entity_id": todo_entity},
                blocking=True,
            )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("todo.add_item failed: %s", type(err).__name__)
            raise TodoAddError(added) from None
        added.append(item)
    return added


async def _async_run_model(call: Awaitable[Extraction]) -> Extraction:
    """Await a provider call under the extraction timeout."""
    try:
        async with asyncio.timeout(EXTRACT_TIMEOUT_SECONDS):
            return await call
    except TimeoutError:
        raise ProviderTimeoutError("The AI took too long to answer") from None


async def async_extract_and_add(
    hass: HomeAssistant,
    provider: Provider,
    todo_entity: str,
    image: bytes,
    mime: str,
    lock: asyncio.Lock | None = None,
) -> list[str]:
    """Extract ingredients from an image and add each to the todo entity."""
    async with lock or asyncio.Lock():
        extraction = await _async_run_model(
            provider.async_extract_from_image(image, mime)
        )
        return await _async_add_extraction(hass, todo_entity, extraction)


async def async_extract_url_and_add(
    hass: HomeAssistant,
    provider: Provider,
    todo_entity: str,
    url: str,
    lock: asyncio.Lock | None = None,
) -> tuple[list[str], str | None]:
    """Fetch a recipe link, extract its ingredients and add them; return (items, title)."""
    async with lock or asyncio.Lock():
        page = await async_fetch_recipe(hass, url)
        if not page.text:
            raise NoIngredientsError
        extraction = await _async_run_model(provider.async_extract_from_text(page.text))
        return await _async_add_extraction(hass, todo_entity, extraction), page.title
