"""Tests for the upload endpoint."""

from unittest.mock import AsyncMock, patch

from aiohttp import FormData
from homeassistant.components.shopping_list.todo import ShoppingTodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.ingredient_extractor.const import (
    API_EXTRACT_URL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TODO_ENTITY,
    DOMAIN,
    MAX_IMAGE_BYTES,
)
from custom_components.ingredient_extractor.providers.base import (
    Extraction,
    Ingredient,
    ProviderAuthError,
    ProviderError,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
EXTRACT = "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_extract_from_image"
RECIPE = Extraction(
    True,
    [
        Ingredient("plain flour", "500", "g"),
        Ingredient("garlic", "2", "cloves"),
        Ingredient("salt and pepper"),
    ],
)


def _form(data: bytes = JPEG, field: str = "image") -> FormData:
    form = FormData()
    form.add_field(field, data, filename="r.jpg", content_type="image/jpeg")
    return form


@pytest.fixture
async def setup(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the integration plus a real shopping list."""
    shopping = MockConfigEntry(domain="shopping_list")
    shopping.add_to_hass(hass)
    assert await hass.config_entries.async_setup(shopping.entry_id)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", "api_key": "test-key"},
        options={CONF_MODEL: "claude-haiku-5-5", CONF_TODO_ENTITY: "todo.shopping_list"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_success(hass, hass_client, setup) -> None:
    """Items are formatted and added to the todo list."""
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(return_value=RECIPE)):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    body = await resp.json()
    assert resp.status == 200
    assert body["ok"] is True
    assert body["items"] == ["500g plain flour", "2 cloves garlic", "salt and pepper"]
    assert body["added"] == 3
    assert body["todo_entity"] == "todo.shopping_list"
    assert isinstance(body["duration_ms"], int)

    result = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.shopping_list"},
        blocking=True, return_response=True,
    )
    summaries = {i["summary"] for i in result["todo.shopping_list"]["items"]}
    assert summaries == set(body["items"])


async def test_no_image_field(hass_client, setup) -> None:
    """A form without `image` is a 400."""
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, data=_form(field="other"))
    assert resp.status == 400
    assert (await resp.json())["error"] == "no_image"


async def test_not_multipart(hass_client, setup) -> None:
    """A JSON body is a 400, not a crash."""
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, json={"a": 1})
    assert resp.status == 400


async def test_empty_file(hass_client, setup) -> None:
    """An empty file is a 400."""
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, data=_form(b""))
    assert resp.status == 400


async def test_too_large(hass_client, setup) -> None:
    """Images over the cap are a 413."""
    client = await hass_client()
    big = JPEG + b"\x00" * MAX_IMAGE_BYTES
    resp = await client.post(API_EXTRACT_URL, data=_form(big))
    assert resp.status == 413
    assert (await resp.json())["error"] == "too_large"


@pytest.mark.parametrize("data", [b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32, b"garbage" * 10])
async def test_unsupported_type(hass_client, setup, data) -> None:
    """HEIC and junk are a 415, whatever the client claims."""
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, data=_form(data))
    assert resp.status == 415
    assert (await resp.json())["error"] == "unsupported_type"


@pytest.mark.parametrize(
    "data",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        b"RIFF\x00\x00\x00\x00WEBPVP8 ",
        b"GIF89a" + b"\x00" * 16,
    ],
)
async def test_other_accepted_types(hass_client, setup, data) -> None:
    """PNG, WebP and GIF pass type detection."""
    client = await hass_client()
    mock = AsyncMock(return_value=RECIPE)
    with patch(EXTRACT, mock):
        resp = await client.post(API_EXTRACT_URL, data=_form(data))
    assert resp.status == 200


@pytest.mark.parametrize(
    ("extraction", "code"),
    [
        (Extraction(False, []), "not_a_recipe"),
        (Extraction(True, []), "no_ingredients"),
    ],
)
async def test_unprocessable(hass_client, setup, extraction, code) -> None:
    """Non-recipes and empty recipes are 422."""
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(return_value=extraction)):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    assert resp.status == 422
    assert (await resp.json())["error"] == code


async def test_provider_auth(hass_client, setup) -> None:
    """A rejected key is 502, never 401."""
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(side_effect=ProviderAuthError("The Anthropic API key was rejected"))):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    assert resp.status == 502
    assert (await resp.json())["error"] == "provider_auth"


async def test_provider_error(hass_client, setup) -> None:
    """Other provider failures are 502 provider_error."""
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(side_effect=ProviderError("boom"))):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    body = await resp.json()
    assert resp.status == 502
    assert body["error"] == "provider_error"
    assert body["message"] == "boom"


async def test_timeout(hass_client, setup) -> None:
    """A slow provider is a 504."""
    client = await hass_client()
    with patch(EXTRACT, AsyncMock(side_effect=TimeoutError)):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    assert resp.status == 504
    assert (await resp.json())["error"] == "timeout"


async def test_todo_error_reports_added(hass, hass_client, setup) -> None:
    """If the todo service fails mid-way, items added so far are returned."""
    real = ShoppingTodoListEntity.async_create_todo_item
    calls = 0

    async def flaky(self, item):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HomeAssistantError("nope")
        return await real(self, item)

    client = await hass_client()
    with patch(EXTRACT, AsyncMock(return_value=RECIPE)), patch.object(
        ShoppingTodoListEntity, "async_create_todo_item", flaky
    ):
        resp = await client.post(API_EXTRACT_URL, data=_form())
    body = await resp.json()
    assert resp.status == 500
    assert body["error"] == "todo_error"
    assert body["items"] == ["500g plain flour"]


async def test_not_configured(hass, hass_client) -> None:
    """With no loaded entry the endpoint is a 503."""
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_client()
    resp = await client.post(API_EXTRACT_URL, data=_form())
    assert resp.status == 503
    assert (await resp.json())["error"] == "not_configured"


async def test_unauthenticated(hass, hass_client_no_auth, setup) -> None:
    """The endpoint requires auth."""
    client = await hass_client_no_auth()
    resp = await client.post(API_EXTRACT_URL, data=_form())
    assert resp.status == 401


async def test_unload(hass, setup) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(setup.entry_id)
