"""Remember each item's shop section and order the todo list by section."""

from __future__ import annotations

import logging

from homeassistant.components.todo import (
    DOMAIN as TODO_DOMAIN,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.storage import Store

from .const import (
    CATEGORIES,
    DOMAIN,
    MAX_CATEGORIZE_ITEMS,
    MAX_STORED_CATEGORIES,
)
from .formatting import item_key
from .providers.base import Provider

_LOGGER = logging.getLogger(__name__)

_RANK = {category: index for index, category in enumerate(CATEGORIES)}
_STORAGE_VERSION = 1
_SAVE_DELAY_SECONDS = 10


class CategoryStore:
    """Item key -> shop section, kept in .storage so each item is classified once."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store; call async_load before use."""
        self._store: Store[dict[str, dict[str, str]]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.categories"
        )
        self._categories: dict[str, str] = {}

    async def async_load(self) -> None:
        """Read the saved categories."""
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("categories"), dict):
            self._categories = {
                str(k): str(v) for k, v in data["categories"].items()
            }

    def get(self, key: str) -> str | None:
        """The remembered section for an item key."""
        return self._categories.get(key)

    def remember(self, key: str, category: str) -> None:
        """Store a section (newest last) and schedule a save."""
        if not key or self._categories.get(key) == category:
            return
        self._categories.pop(key, None)
        self._categories[key] = category
        while len(self._categories) > MAX_STORED_CATEGORIES:
            del self._categories[next(iter(self._categories))]
        self._store.async_delay_save(
            lambda: {"categories": self._categories}, _SAVE_DELAY_SECONDS
        )


def get_todo_entity(hass: HomeAssistant, entity_id: str) -> TodoListEntity | None:
    """The todo entity object, or None if it isn't loaded."""
    component: EntityComponent[TodoListEntity] | None = hass.data.get(TODO_DOMAIN)
    return component.get_entity(entity_id) if component else None


async def async_sort_list(
    hass: HomeAssistant, provider: Provider, store: CategoryStore, todo_entity: str
) -> int:
    """Order the open items by shop section; return how many were moved.

    Items with no remembered section are classified first, in one call. Ticked items
    stay below the open ones in their current order.
    """
    entity = get_todo_entity(hass, todo_entity)
    if entity is None or not (
        (entity.supported_features or 0) & TodoListEntityFeature.MOVE_TODO_ITEM
    ):
        raise HomeAssistantError(f"{todo_entity} can't be reordered")

    items = [i for i in (entity.todo_items or []) if i.uid and i.summary]
    open_items = [i for i in items if i.status == TodoItemStatus.NEEDS_ACTION]
    keys = [item_key(i.summary) for i in open_items]

    unknown: dict[str, str] = {}
    for item, key in zip(open_items, keys):
        if key and store.get(key) is None and key not in unknown:
            unknown[key] = item.summary
    if unknown:
        batch = list(unknown.items())[:MAX_CATEGORIZE_ITEMS]
        categories = await provider.async_categorize([text for _, text in batch])
        for (key, _), category in zip(batch, categories):
            store.remember(key, category)

    ranked = sorted(
        range(len(open_items)),
        key=lambda i: _RANK.get(store.get(keys[i]) or "", len(_RANK)),
    )
    desired = [open_items[i].uid for i in ranked]
    desired += [i.uid for i in items if i.status != TodoItemStatus.NEEDS_ACTION]

    current = [i.uid for i in items]
    moved = 0
    for position, uid in enumerate(desired):
        if current[position] == uid:
            continue
        await entity.async_move_todo_item(
            uid=uid, previous_uid=desired[position - 1] if position else None
        )
        current.remove(uid)
        current.insert(position, uid)
        moved += 1
    _LOGGER.debug("Sorted %s: %d moves", todo_entity, moved)
    return moved
