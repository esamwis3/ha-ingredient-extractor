"""Orchestrates one extraction: provider call, formatting, adding to the todo list."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
import logging

import voluptuous as vol

from homeassistant.components.todo import TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import EXTRACT_TIMEOUT_SECONDS
from .fetch import async_fetch_recipe
from .formatting import format_item, item_key, merge_items
from .models import IngredientExtractorData
from .providers.base import Extraction, ProviderError, ProviderTimeoutError
from .sorting import async_sort_list, get_todo_entity

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
    runtime: IngredientExtractorData,
    extraction: Extraction,
) -> list[str]:
    """Add each item to the todo list, combining it with an open entry of the same item.

    Returns the text of every entry added or changed, in extraction order.
    """
    if not extraction.is_recipe:
        raise NotARecipeError
    pairs = [(text, ing) for ing in extraction.ingredients if (text := format_item(ing))]
    if not pairs:
        raise NoIngredientsError

    # Open entries by item key: (uid or None if added just now, current text).
    entity = get_todo_entity(hass, runtime.todo_entity)
    open_items: dict[str, tuple[str | None, str]] = {}
    for todo in (entity.todo_items or []) if entity else []:
        if todo.status == TodoItemStatus.NEEDS_ACTION and todo.summary:
            open_items.setdefault(item_key(todo.summary), (todo.uid, todo.summary))

    added: list[str] = []
    for text, ing in pairs:
        key = item_key(text)
        if ing.category:
            runtime.categories.remember(key, ing.category)
        uid, current = open_items.get(key, (None, None))
        merged = merge_items(current, text) if current is not None else None
        try:
            if merged is None:
                await _async_call_todo(hass, runtime, "add_item", {"item": text})
                open_items.setdefault(key, (None, text))
                added.append(text)
                continue
            if merged != current:
                await _async_call_todo(
                    hass,
                    runtime,
                    "update_item",
                    {"item": uid or _uid_of(entity, current), "rename": merged},
                )
                open_items[key] = (uid, merged)
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("Updating the todo list failed: %s", type(err).__name__)
            raise TodoAddError(added) from None
        added = [t for t in added if t != current]
        added.append(merged)
    return added


def _uid_of(entity: TodoListEntity | None, summary: str) -> str:
    """The uid of the open entry with this text (falls back to the text itself)."""
    for todo in (entity.todo_items or []) if entity else []:
        if todo.summary == summary and todo.status == TodoItemStatus.NEEDS_ACTION:
            return todo.uid or summary
    return summary


async def _async_call_todo(
    hass: HomeAssistant, runtime: IngredientExtractorData, service: str, data: dict
) -> None:
    await hass.services.async_call(
        "todo", service, data, target={"entity_id": runtime.todo_entity}, blocking=True
    )


async def _async_add_and_sort(
    hass: HomeAssistant, runtime: IngredientExtractorData, extraction: Extraction
) -> list[str]:
    """Add the items, then sort the list if auto-sort is on. A failed sort is not fatal."""
    items = await _async_add_extraction(hass, runtime, extraction)
    if runtime.auto_sort:
        try:
            await async_sort_list(
                hass, runtime.provider, runtime.categories, runtime.todo_entity
            )
        except (ProviderError, HomeAssistantError) as err:
            _LOGGER.warning("Sorting the list failed: %s", err)
    return items


async def _async_run_model(call: Awaitable[Extraction]) -> Extraction:
    """Await a provider call under the extraction timeout."""
    try:
        async with asyncio.timeout(EXTRACT_TIMEOUT_SECONDS):
            return await call
    except TimeoutError:
        raise ProviderTimeoutError("The AI took too long to answer") from None


async def async_extract_and_add(
    hass: HomeAssistant,
    runtime: IngredientExtractorData,
    image: bytes,
    mime: str,
) -> list[str]:
    """Extract ingredients from an image and add each to the todo entity."""
    async with runtime.lock:
        extraction = await _async_run_model(
            runtime.provider.async_extract_from_image(image, mime)
        )
        return await _async_add_and_sort(hass, runtime, extraction)


async def async_extract_url_and_add(
    hass: HomeAssistant,
    runtime: IngredientExtractorData,
    url: str,
) -> tuple[list[str], str | None]:
    """Fetch a recipe link, extract its ingredients and add them; return (items, title)."""
    async with runtime.lock:
        page = await async_fetch_recipe(hass, url)
        if not page.text:
            raise NoIngredientsError
        extraction = await _async_run_model(
            runtime.provider.async_extract_from_text(page.text)
        )
        return await _async_add_and_sort(hass, runtime, extraction), page.title
