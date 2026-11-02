"""Tests for the config and options flows."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.ingredient_extractor.const import (
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TODO_ENTITY,
    DOMAIN,
)
from custom_components.ingredient_extractor.providers.anthropic import AnthropicProvider
from custom_components.ingredient_extractor.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderModelError,
    ProviderTimeoutError,
)

USER_INPUT = {CONF_PROVIDER: "anthropic", CONF_API_KEY: "test-key", CONF_MODEL: "claude-haiku-5-5"}
VALIDATE = "custom_components.ingredient_extractor.providers.anthropic.AnthropicProvider.async_validate"


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid key creates the entry with default options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with patch(VALIDATE), patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Anthropic Claude"
    assert result["data"] == {CONF_PROVIDER: "anthropic", CONF_API_KEY: "test-key"}
    assert result["options"] == {
        CONF_MODEL: "claude-haiku-5-5",
        CONF_TODO_ENTITY: "todo.shopping_list",
    }


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (ProviderAuthError("x"), "invalid_auth"),
        (ProviderTimeoutError("x"), "cannot_connect"),
        (ProviderError("x"), "cannot_connect"),
        (ProviderModelError("x"), "invalid_model"),
        (RuntimeError("x"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recovers(hass: HomeAssistant, exc, error) -> None:
    """Validation errors show on the form and can be retried."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(VALIDATE, side_effect=exc):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with patch(VALIDATE), patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_single_instance(hass: HomeAssistant) -> None:
    """Only one entry is allowed."""
    MockConfigEntry(domain=DOMAIN, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reconfigure(hass: HomeAssistant) -> None:
    """Reconfigure updates the key and model."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", CONF_API_KEY: "old-key"},
        options={CONF_MODEL: "claude-haiku-5-5", CONF_TODO_ENTITY: "todo.shopping_list"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    with patch(VALIDATE), patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "new-key", CONF_MODEL: "claude-sonnet-5-5"},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == "new-key"
    assert entry.options[CONF_MODEL] == "claude-sonnet-5-5"
    assert entry.options[CONF_TODO_ENTITY] == "todo.shopping_list"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Options flow saves model, todo entity and the share and sort switches."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", CONF_API_KEY: "test-key"},
        options={CONF_MODEL: "claude-haiku-5-5", CONF_TODO_ENTITY: "todo.shopping_list"},
    )
    entry.add_to_hass(hass)
    with patch(VALIDATE) as validate, patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        share = next(k for k in result["data_schema"].schema if k == "share_enabled")
        assert share.default() is True
        sort = next(k for k in result["data_schema"].schema if k == "auto_sort")
        assert sort.default() is True
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_MODEL: "claude-sonnet-5-5",
                CONF_TODO_ENTITY: "todo.groceries",
                "share_enabled": False,
                "auto_sort": False,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_MODEL: "claude-sonnet-5-5",
        CONF_TODO_ENTITY: "todo.groceries",
        "share_enabled": False,
        "auto_sort": False,
    }
    # The model changed, so it was checked against the existing key.
    validate.assert_awaited_once()
    assert entry.data[CONF_API_KEY] == "test-key"


def _options_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROVIDER: "anthropic", CONF_API_KEY: "old-key"},
        options={
            CONF_MODEL: "claude-haiku-5-5",
            CONF_TODO_ENTITY: "todo.shopping_list",
            "share_enabled": True,
            "auto_sort": True,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_options_flow_new_api_key(hass: HomeAssistant) -> None:
    """A new key is validated, saved, confirmed, and kept out of the options."""
    entry = _options_entry(hass)
    with patch(VALIDATE) as validate, patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ), patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_API_KEY: " new-key ", **entry.options, "auto_sort": False},
        )
        # Saved before the confirmation is shown, so closing it keeps the key.
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "api_key_valid"
        assert result["description_placeholders"] == {"key_hint": "-key"}
        assert entry.data[CONF_API_KEY] == "new-key"
        assert entry.options["auto_sort"] is False
        reload.assert_called_once_with(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    validate.assert_awaited_once()
    assert CONF_API_KEY not in entry.options
    assert entry.options["auto_sort"] is False
    # The final step changes nothing, so no second reload.
    reload.assert_called_once()


async def test_options_flow_blank_key_skips_validation(hass: HomeAssistant) -> None:
    """Saving with no new key and the same model does not call the provider."""
    entry = _options_entry(hass)
    with patch(VALIDATE) as validate, patch(
        "custom_components.ingredient_extractor.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**entry.options, "auto_sort": False}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    validate.assert_not_called()
    assert entry.data[CONF_API_KEY] == "old-key"


async def test_options_flow_rejects_bad_key(hass: HomeAssistant) -> None:
    """A rejected key shows an error and nothing is saved."""
    entry = _options_entry(hass)
    with patch(VALIDATE, side_effect=ProviderAuthError("nope")):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {**entry.options, CONF_API_KEY: "bad-key", "auto_sort": False},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_API_KEY] == "old-key"
    assert entry.options["auto_sort"] is True


def test_provider_metadata() -> None:
    """Provider defaults are what the contract says."""
    assert AnthropicProvider.default_model == "claude-haiku-5-5"
    assert "claude-sonnet-5-5" in AnthropicProvider.suggested_models()
