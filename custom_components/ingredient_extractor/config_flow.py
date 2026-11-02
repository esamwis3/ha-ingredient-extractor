"""Config and options flow for Ingredient Extractor."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_AUTO_SORT,
    CONF_SHARE_ENABLED,
    CONF_TODO_ENTITY,
    DEFAULT_PROVIDER,
    DEFAULT_TODO_ENTITY,
    DOMAIN,
)
from .providers import PROVIDERS, get_provider_class
from .providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderModelError,
    ProviderTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


def _model_selector(models: list[str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(options=models, custom_value=True, sort=False)
    )


async def _async_validate(
    hass: HomeAssistant, provider_key: str, api_key: str, model: str
) -> dict[str, str]:
    """Return form errors (empty when the key and model work)."""
    provider = get_provider_class(provider_key)(hass, api_key, model)
    try:
        await provider.async_validate()
    except ProviderAuthError:
        return {"base": "invalid_auth"}
    except ProviderModelError:
        return {"base": "invalid_model"}
    except (ProviderTimeoutError, ProviderError):
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error validating credentials")
        return {"base": "unknown"}
    return {}


class IngredientExtractorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def _async_validate(
        self, provider_key: str, api_key: str, model: str
    ) -> dict[str, str]:
        """Return form errors (empty when the key and model work)."""
        return await _async_validate(self.hass, provider_key, api_key, model)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for provider, API key and model."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(
                user_input[CONF_PROVIDER],
                user_input[CONF_API_KEY],
                user_input[CONF_MODEL],
            )
            if not errors:
                provider_cls = get_provider_class(user_input[CONF_PROVIDER])
                return self.async_create_entry(
                    title=provider_cls.name,
                    data={
                        CONF_PROVIDER: user_input[CONF_PROVIDER],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                    },
                    options={
                        CONF_MODEL: user_input[CONF_MODEL],
                        CONF_TODO_ENTITY: DEFAULT_TODO_ENTITY,
                    },
                )

        default_cls = get_provider_class(DEFAULT_PROVIDER)
        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER, default=DEFAULT_PROVIDER): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": key, "label": cls.name}
                            for key, cls in PROVIDERS.items()
                        ]
                    )
                ),
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_MODEL,
                    default=(user_input or {}).get(CONF_MODEL, default_cls.default_model),
                ): _model_selector(default_cls.suggested_models()),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the API key or model."""
        entry = self._get_reconfigure_entry()
        provider_key = entry.data[CONF_PROVIDER]
        provider_cls = get_provider_class(provider_key)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(
                provider_key, user_input[CONF_API_KEY], user_input[CONF_MODEL]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                    options={**entry.options, CONF_MODEL: user_input[CONF_MODEL]},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_MODEL,
                    default=entry.options.get(CONF_MODEL, provider_cls.default_model),
                ): _model_selector(provider_cls.suggested_models()),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> IngredientExtractorOptionsFlow:
        """Return the options flow."""
        return IngredientExtractorOptionsFlow()


class IngredientExtractorOptionsFlow(OptionsFlowWithReload):
    """Edit the API key, model and target todo list."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show or save options."""
        entry = self.config_entry
        provider_key = entry.data[CONF_PROVIDER]
        provider_cls = get_provider_class(provider_key)
        opts = entry.options
        errors: dict[str, str] = {}
        if user_input is not None:
            options = dict(user_input)
            new_key = (options.pop(CONF_API_KEY, None) or "").strip()
            model = options[CONF_MODEL]
            # Only call the provider when something it checks has changed.
            if new_key or model != opts.get(CONF_MODEL):
                errors = await _async_validate(
                    self.hass, provider_key, new_key or entry.data[CONF_API_KEY], model
                )
            if not errors:
                if not new_key:
                    return self.async_create_entry(data=options)
                # Save now, so closing the confirmation still keeps the key.
                # The automatic reload only fires on the final step's options
                # change, which this pre-empts, so reload here.
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_API_KEY: new_key}, options=options
                )
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                self._saved_options = options
                self._key_hint = new_key[-4:]
                return await self.async_step_api_key_valid()
            opts = {**opts, **options}

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_MODEL, default=opts.get(CONF_MODEL, provider_cls.default_model)
                ): _model_selector(provider_cls.suggested_models()),
                vol.Required(
                    CONF_TODO_ENTITY,
                    default=opts.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY),
                ): EntitySelector(EntitySelectorConfig(domain="todo")),
                vol.Required(
                    CONF_SHARE_ENABLED, default=opts.get(CONF_SHARE_ENABLED, True)
                ): bool,
                vol.Required(
                    CONF_AUTO_SORT, default=opts.get(CONF_AUTO_SORT, True)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_api_key_valid(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm that the new key was accepted and saved."""
        if user_input is not None:
            return self.async_create_entry(data=self._saved_options)
        return self.async_show_form(
            step_id="api_key_valid",
            data_schema=vol.Schema({}),
            description_placeholders={"key_hint": self._key_hint},
            last_step=True,
        )
