"""Tests for merging duplicates and sorting the list by shop section."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from aiohttp import FormData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
import pytest

from custom_components.ingredient_extractor.const import (
    API_EXTRACT_URL,
    CONF_AUTO_SORT,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TODO_ENTITY,
    DOMAIN,
    SERVICE_SORT_LIST,
)
from custom_components.ingredient_extractor.providers.base import (
    Extraction,
    Ingredient,
    ProviderError,
)

EXTRACT = "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_extract_from_image"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def _setup(hass: HomeAssistant, auto_sort: bool = True) -> MockConfigEntry:
    shopping = MockConfigEntry(domain="shopping_list")
    shopping.add_to_hass(hass)
    assert await hass.config_entries.async_setup(shopping.entry_id)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", "api_key": "test-key"},
        options={
            CONF_MODEL: "claude-haiku-5-5",
            CONF_TODO_ENTITY: "todo.shopping_list",
            CONF_AUTO_SORT: auto_sort,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _add(hass: HomeAssistant, *names: str) -> None:
    for name in names:
        await hass.services.async_call(
            "todo", "add_item", {"item": name},
            target={"entity_id": "todo.shopping_list"}, blocking=True,
        )


async def _items(hass: HomeAssistant) -> list[tuple[str, str]]:
    result = await hass.services.async_call(
        "todo", "get_items", {"status": ["needs_action", "completed"]},
        target={"entity_id": "todo.shopping_list"}, blocking=True, return_response=True,
    )
    return [(i["summary"], i["status"]) for i in result["todo.shopping_list"]["items"]]


async def _post(hass_client, extraction: Extraction) -> dict:
    form = FormData()
    form.add_field("image", JPEG, filename="r.jpg", content_type="image/jpeg")
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(return_value=extraction)):
        resp = await client.post(API_EXTRACT_URL, data=form)
    assert resp.status == 200
    return await resp.json()


async def test_merges_with_open_items(hass, hass_client) -> None:
    """Duplicates of open entries are combined; a ticked entry is left alone."""
    await _setup(hass, auto_sort=False)
    await _add(hass, "500g plain flour", "milk", "2 tbsp olive oil", "eggs")
    await hass.services.async_call(
        "todo", "update_item", {"item": "eggs", "status": "completed"},
        target={"entity_id": "todo.shopping_list"}, blocking=True,
    )
    body = await _post(
        hass_client,
        Extraction(
            True,
            [
                Ingredient("plain flour", "200", "g"),
                Ingredient("milk", "500", "ml"),
                Ingredient("olive oil", "100", "ml"),
                Ingredient("eggs", "2"),
                Ingredient("garlic", "2", "cloves"),
                Ingredient("garlic", "1", "clove"),
            ],
        ),
    )
    assert body["items"] == [
        "700g plain flour",
        "500ml milk",
        "100ml olive oil",
        "2 eggs",
        "3 cloves garlic",
    ]
    assert await _items(hass) == [
        ("700g plain flour", "needs_action"),
        ("500ml milk", "needs_action"),
        ("2 tbsp olive oil", "needs_action"),
        ("eggs", "completed"),
        ("100ml olive oil", "needs_action"),
        ("2 eggs", "needs_action"),
        ("3 cloves garlic", "needs_action"),
    ]


async def test_bare_duplicate_is_not_added(hass, hass_client) -> None:
    """A list line already on the list (no amounts) is not added twice."""
    await _setup(hass, auto_sort=False)
    await _add(hass, "milk")
    body = await _post(hass_client, Extraction(True, [Ingredient("milk"), Ingredient("bread")]))
    assert body["items"] == ["milk", "bread"]
    assert [s for s, _ in await _items(hass)] == ["milk", "bread"]


async def test_auto_sort_after_extraction(hass, hass_client) -> None:
    """Extracted items use their own category; hand-typed items are classified once."""
    await _setup(hass)
    await _add(hass, "bin bags", "apples")
    calls: list[list[str]] = []

    async def fake(self, names):
        calls.append(list(names))
        return ["Household" if "bin" in n else "Fruit" for n in names]

    with patch(
        "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_categorize",
        fake,
    ):
        await _post(
            hass_client,
            Extraction(
                True,
                [
                    Ingredient("bread", category="Bread"),
                    Ingredient("onions", "2", category="Vegetables"),
                    Ingredient("mince", "500", "g", category="Meat"),
                    Ingredient("mystery", category="Other"),
                ],
            ),
        )
        assert [s for s, _ in await _items(hass)] == [
            "2 onions", "apples", "500g mince", "bin bags", "bread", "mystery",
        ]
        assert calls == [["bin bags", "apples"]]

        # Remembered: sorting again needs no AI call.
        await _add(hass, "1 lime")
        resp = await hass.services.async_call(
            DOMAIN, SERVICE_SORT_LIST, {}, blocking=True, return_response=True
        )
    assert calls[1:] == [["1 lime"]]
    assert resp["moved"] >= 1
    assert [s for s, _ in await _items(hass)][:3] == ["2 onions", "apples", "1 lime"]


async def test_sort_keeps_ticked_items_last(hass) -> None:
    """Ticked items stay below the open ones."""
    await _setup(hass, auto_sort=False)
    await _add(hass, "eggs", "bread", "carrots")
    await hass.services.async_call(
        "todo", "update_item", {"item": "eggs", "status": "completed"},
        target={"entity_id": "todo.shopping_list"}, blocking=True,
    )
    with patch(
        "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_categorize",
        AsyncMock(return_value=["Bread", "Vegetables"]),
    ):
        await hass.services.async_call(DOMAIN, SERVICE_SORT_LIST, {}, blocking=True)
    assert await _items(hass) == [
        ("carrots", "needs_action"),
        ("bread", "needs_action"),
        ("eggs", "completed"),
    ]


async def test_sort_failure(hass, hass_client) -> None:
    """A failed classification fails the action, but never an extraction."""
    await _setup(hass)
    with patch(
        "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_categorize",
        AsyncMock(side_effect=ProviderError("boom")),
    ):
        body = await _post(hass_client, Extraction(True, [Ingredient("bread")]))
        assert body["items"] == ["bread"]
        with pytest.raises(HomeAssistantError, match="boom"):
            await hass.services.async_call(DOMAIN, SERVICE_SORT_LIST, {}, blocking=True)


async def test_categories_survive_reload(hass, hass_storage) -> None:
    """Remembered categories outlive a reload and are saved to storage."""
    entry = await _setup(hass, auto_sort=False)
    entry.runtime_data.categories.remember("bread", "Bread")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.categories.get("bread") == "Bread"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert hass_storage[f"{DOMAIN}.categories"]["data"] == {"categories": {"bread": "Bread"}}


async def test_categories_loaded_from_storage(hass, hass_storage) -> None:
    """Saved categories are used on start."""
    hass_storage[f"{DOMAIN}.categories"] = {
        "version": 1, "key": f"{DOMAIN}.categories", "data": {"categories": {"egg": "Dairy"}},
    }
    entry = await _setup(hass, auto_sort=False)
    assert entry.runtime_data.categories.get("egg") == "Dairy"
