"""Orchestrates one extraction: provider call, formatting, adding to the todo list."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import EXTRACT_TIMEOUT_SECONDS
from .formatting import format_item
from .providers.base import Provider, ProviderTimeoutError

_LOGGER = logging.getLogger(__name__)


class NotARecipeError(Exception):
    """The image does not show a recipe."""


class NoIngredientsError(Exception):
    """A recipe was recognised but no ingredients could be read."""


class TodoAddError(Exception):
    """Adding to the todo list failed part-way."""

    def __init__(self, added: list[str]) -> None:
        """Keep the items that were added before the failure."""
        super().__init__("Could not add items to the todo list")
        self.added = added


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
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT_SECONDS):
                extraction = await provider.async_extract_from_image(image, mime)
        except TimeoutError:
            raise ProviderTimeoutError("The AI took too long to answer") from None

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
