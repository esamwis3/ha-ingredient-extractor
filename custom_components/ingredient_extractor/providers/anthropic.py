"""Anthropic Claude provider (official SDK, structured JSON output)."""

from __future__ import annotations

import base64
from functools import partial
import json
import logging
from typing import Any

import anthropic

from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

from ..const import MAX_INGREDIENTS
from ..schema import (
    CATEGORIZE_SCHEMA,
    CATEGORIZE_SYSTEM_PROMPT,
    INGREDIENTS_SCHEMA,
    SYSTEM_PROMPT,
    TEXT_USER_PROMPT,
    USER_PROMPT,
    categorize_prompt,
    parse_categories,
    parse_extraction,
)
from .base import (
    Extraction,
    Provider,
    ProviderAuthError,
    ProviderError,
    ProviderModelError,
    ProviderTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class AnthropicProvider(Provider):
    """Read ingredients from an image with a Claude model."""

    key = "anthropic"
    name = "Anthropic Claude"
    default_model = "claude-haiku-5-5"

    def __init__(self, hass: HomeAssistant, api_key: str, model: str) -> None:
        """Initialize; the SDK client is built lazily (it does blocking I/O)."""
        super().__init__(hass, api_key, model)
        self._client: anthropic.AsyncAnthropic | None = None

    @classmethod
    def suggested_models(cls) -> list[str]:
        """Models offered in the config flow."""
        return ["claude-haiku-5-5", "claude-sonnet-5-5"]

    async def _async_client(self) -> anthropic.AsyncAnthropic:
        """Build the client in the executor, sharing HA's httpx client."""
        if self._client is None:
            self._client = await self.hass.async_add_executor_job(
                partial(
                    anthropic.AsyncAnthropic,
                    api_key=self._api_key,
                    http_client=get_async_client(self.hass),
                )
            )
        return self._client

    async def async_validate(self) -> None:
        """Check the key and model with a free metadata call."""
        client = await self._async_client()
        try:
            await client.models.retrieve(self.model)
        except anthropic.AnthropicError as err:
            raise self._map_error(err) from None

    async def async_extract_from_image(self, image: bytes, mime_type: str) -> Extraction:
        """Send the image to Claude and parse the structured answer."""
        b64 = base64.standard_b64encode(image).decode("ascii")
        try:
            return await self._async_extract(
                [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime_type, "data": b64},
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
                "image",
            )
        finally:
            del b64

    async def async_extract_from_text(self, text: str) -> Extraction:
        """Send scraped page text to Claude and parse the structured answer."""
        # The page cannot close the wrapper tag early and smuggle text outside it.
        wrapped = TEXT_USER_PROMPT.format(text=text.replace("</recipe_page>", ""))
        return await self._async_extract([{"type": "text", "text": wrapped}], "page")

    async def async_categorize(self, names: list[str]) -> list[str]:
        """Ask Claude for the shop section of each item."""
        if not names:
            return []
        data = await self._async_structured(
            CATEGORIZE_SYSTEM_PROMPT,
            [{"type": "text", "text": categorize_prompt(names)}],
            CATEGORIZE_SCHEMA,
            "list",
        )
        return parse_categories(data, len(names))

    async def _async_extract(self, content: list[dict], what: str) -> Extraction:
        """Run the ingredients call and validate the answer."""
        data = await self._async_structured(SYSTEM_PROMPT, content, INGREDIENTS_SCHEMA, what)
        return parse_extraction(data, MAX_INGREDIENTS)

    async def _async_structured(
        self, system: str, content: list[dict], schema: dict, what: str
    ) -> Any:
        """Run one structured-output call and return the decoded JSON."""
        client = await self._async_client()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                thinking={"type": "disabled"},
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AnthropicError as err:
            raise self._map_error(err) from None

        if response.stop_reason == "refusal":
            raise ProviderError(f"The AI declined to read this {what}")
        if response.stop_reason == "max_tokens":
            raise ProviderError("The AI's answer was cut off; try a smaller recipe")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderError("The AI returned an unexpected response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ProviderError("The AI returned an unreadable response") from None

    def _map_error(self, err: anthropic.AnthropicError) -> ProviderError:
        """Convert SDK exceptions to safe messages (never headers, bodies or keys)."""
        _LOGGER.debug("Anthropic call failed: %s", type(err).__name__)
        if isinstance(
            err, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)
        ):
            return ProviderAuthError("The Anthropic API key was rejected")
        if isinstance(err, anthropic.NotFoundError):
            return ProviderModelError(f"Unknown model {self.model}")
        if isinstance(err, anthropic.APITimeoutError):
            return ProviderTimeoutError("The AI took too long to answer")
        if isinstance(err, anthropic.RateLimitError):
            return ProviderError("Anthropic rate limit reached; try again shortly")
        if isinstance(err, anthropic.APIStatusError):
            return ProviderError(f"Anthropic returned an error (HTTP {err.status_code})")
        if isinstance(err, anthropic.APIConnectionError):
            return ProviderError("Could not reach the Anthropic API")
        return ProviderError("The Anthropic request failed")
