"""Tests for the link flow: HTTP JSON branch and the mobile_app.share listener."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import Context, HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
import pytest

from custom_components.ingredient_extractor.const import (
    API_EXTRACT_URL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TODO_ENTITY,
    DOMAIN,
)
from custom_components.ingredient_extractor.fetch import (
    BlockedUrlError,
    FetchError,
    RecipePage,
)
from custom_components.ingredient_extractor.providers.base import (
    Extraction,
    Ingredient,
)

FETCH = "custom_components.ingredient_extractor.extractor.async_fetch_recipe"
EXTRACT_TEXT = "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_extract_from_text"
PERSISTENT = "custom_components.ingredient_extractor.share.persistent_notification.async_create"
PAGE = RecipePage("Chicken Curry", "Recipe: Chicken Curry\nIngredients:\n- 2 onions", True)
RECIPE = Extraction(True, [Ingredient("onions", "2"), Ingredient("salt and pepper")])


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    shopping = MockConfigEntry(domain="shopping_list")
    shopping.add_to_hass(hass)
    assert await hass.config_entries.async_setup(shopping.entry_id)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", "api_key": "test-key"},
        options={
            CONF_MODEL: "claude-haiku-5-5",
            CONF_TODO_ENTITY: "todo.shopping_list",
            **options,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def setup(hass: HomeAssistant) -> MockConfigEntry:
    """Integration plus a real shopping list (its storage file is shared; empty it after)."""
    entry = await _setup(hass)
    yield entry
    if items := await _summaries(hass):
        await hass.services.async_call(
            "todo", "remove_item", {"item": list(items)},
            target={"entity_id": "todo.shopping_list"}, blocking=True,
        )


async def _summaries(hass: HomeAssistant) -> set[str]:
    result = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.shopping_list"},
        blocking=True, return_response=True,
    )
    return {i["summary"] for i in result["todo.shopping_list"]["items"]}


# --- HTTP JSON branch -------------------------------------------------------


async def test_link_success(hass, hass_client, setup) -> None:
    """A JSON url is fetched, extracted and added; the title is returned."""
    client = await hass_client()
    with patch(FETCH, AsyncMock(return_value=PAGE)), patch(
        EXTRACT_TEXT, AsyncMock(return_value=RECIPE)
    ) as extract:
        resp = await client.post(API_EXTRACT_URL, json={"url": "https://example.com/r"})
    body = await resp.json()
    assert resp.status == 200
    assert body["ok"] and body["title"] == "Chicken Curry"
    assert body["items"] == ["2 onions", "salt and pepper"]
    extract.assert_awaited_once_with(PAGE.text)
    assert {"2 onions", "salt and pepper"} <= await _summaries(hass)


@pytest.mark.parametrize("payload", [{}, {"url": ""}, {"url": 5}, {"url": "ftp://example.com"}, [1]])
async def test_link_invalid_url(hass, hass_client, setup, payload) -> None:
    """Missing or non-http(s) URLs are rejected before any network access."""
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, json=payload)
    body = await resp.json()
    assert resp.status == 400 and body["error"] == "invalid_url"


async def test_link_blocked_and_fetch_failed(hass, hass_client, setup) -> None:
    """SSRF and fetch failures map to their own codes."""
    client = await hass_client()
    with patch(FETCH, AsyncMock(side_effect=BlockedUrlError)):
        resp = await client.post(API_EXTRACT_URL, json={"url": "http://10.20.30.40/"})
    assert resp.status == 400 and (await resp.json())["error"] == "blocked_url"

    with patch(FETCH, AsyncMock(side_effect=FetchError("Couldn't open that page (HTTP 403)."))):
        resp = await client.post(API_EXTRACT_URL, json={"url": "https://example.com/"})
    body = await resp.json()
    assert resp.status == 502 and body["error"] == "fetch_failed"
    assert "HTTP 403" in body["message"]


async def test_link_not_a_recipe_and_empty_page(hass, hass_client, setup) -> None:
    """Non-recipes and empty pages give the usual 422 codes."""
    client = await hass_client()
    with patch(FETCH, AsyncMock(return_value=PAGE)), patch(
        EXTRACT_TEXT, AsyncMock(return_value=Extraction(False))
    ):
        resp = await client.post(API_EXTRACT_URL, json={"url": "https://example.com/"})
    assert resp.status == 422 and (await resp.json())["error"] == "not_a_recipe"

    empty = RecipePage(None, "", False)
    with patch(FETCH, AsyncMock(return_value=empty)):
        resp = await client.post(API_EXTRACT_URL, json={"url": "https://example.com/"})
    assert resp.status == 422 and (await resp.json())["error"] == "no_ingredients"


# --- mobile_app.share -------------------------------------------------------


def _mobile(hass, user_id, name, os_name) -> None:
    MockConfigEntry(
        domain="mobile_app",
        data={"user_id": user_id, "device_name": name, "os_name": os_name},
    ).add_to_hass(hass)


async def test_share_notifies_android_only_deduped(hass, setup) -> None:
    """Only the sharer's Android apps are notified, once per service name."""
    _mobile(hass, "user-1", "Test Phone", "Android")
    _mobile(hass, "user-1", "Test Phone", "android")  # duplicate registration
    _mobile(hass, "user-1", "Test Pad", "iOS")
    _mobile(hass, "user-2", "Other Phone", "Android")
    _mobile(hass, "user-1", "Gone Phone", "Android")  # no notify service
    calls = {
        name: async_mock_service(hass, "notify", name)
        for name in ("mobile_app_test_phone", "mobile_app_test_pad", "mobile_app_other_phone")
    }
    with patch(FETCH, AsyncMock(return_value=PAGE)), patch(
        EXTRACT_TEXT, AsyncMock(return_value=RECIPE)
    ):
        hass.bus.async_fire(
            "mobile_app.share",
            {"caller": "x", "subject": "Curry", "text": "Look: https://example.com/r. yum"},
            context=Context(user_id="user-1"),
        )
        await hass.async_block_till_done(wait_background_tasks=True)

    assert {"2 onions", "salt and pepper"} <= await _summaries(hass)
    assert len(calls["mobile_app_test_phone"]) == 1
    sent = calls["mobile_app_test_phone"][0].data
    assert sent["message"] == "Added 2 items from Chicken Curry"
    assert sent["title"] == "Shopping list"
    assert not calls["mobile_app_test_pad"] and not calls["mobile_app_other_phone"]


async def test_share_failure_message_and_persistent_fallback(hass, setup) -> None:
    """With no Android service, the friendly error goes to a persistent notification."""
    with patch(
        FETCH, AsyncMock(side_effect=FetchError("Couldn't open that page (HTTP 403)."))
    ), patch(PERSISTENT) as persistent:
        hass.bus.async_fire(
            "mobile_app.share",
            {"url": "https://example.com/r"},
            context=Context(user_id="user-1"),
        )
        await hass.async_block_till_done(wait_background_tasks=True)
    persistent.assert_called_once()
    assert "HTTP 403" in persistent.call_args.args[1]


async def test_share_without_url_ignored(hass, setup) -> None:
    """Events with no http(s) link do nothing."""
    with patch(FETCH, AsyncMock()) as fetch, patch(PERSISTENT) as persistent:
        hass.bus.async_fire(
            "mobile_app.share", {"text": "just words", "subject": "x"}, context=Context(user_id="u")
        )
        await hass.async_block_till_done(wait_background_tasks=True)
    fetch.assert_not_called()
    persistent.assert_not_called()


async def test_share_disabled_no_listener(hass) -> None:
    """share_enabled=False registers no listener."""
    await _setup(hass, share_enabled=False)
    with patch(FETCH, AsyncMock(return_value=PAGE)) as fetch:
        hass.bus.async_fire("mobile_app.share", {"url": "https://example.com/r"})
        await hass.async_block_till_done(wait_background_tasks=True)
    fetch.assert_not_called()
