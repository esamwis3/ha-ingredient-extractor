"""Provider interface shared by every AI backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class Ingredient:
    """One ingredient as returned by the model, before formatting."""

    name: str
    quantity: str | None = None
    unit: str | None = None
    #: Metric alternative printed alongside, e.g. "908" "g" for "2 lbs (908 g)".
    metric_quantity: str | None = None
    metric_unit: str | None = None
    #: Shop section, one of const.CATEGORIES or CATEGORY_OTHER.
    category: str | None = None


@dataclass(frozen=True, slots=True)
class Extraction:
    """Validated model output."""

    is_recipe: bool
    ingredients: list[Ingredient] = field(default_factory=list)


class ProviderError(Exception):
    """Generic provider failure. The message must be safe to show a user."""


class ProviderAuthError(ProviderError):
    """The API key was rejected."""


class ProviderModelError(ProviderError):
    """The configured model does not exist or is not available."""


class ProviderTimeoutError(ProviderError):
    """The provider did not answer in time."""


class Provider(ABC):
    """An AI backend that can read ingredients from an image.

    Implementations must never log or retain the image bytes or the API key.
    """

    #: Registry key, stored in the config entry.
    key: str
    #: Human-readable name for the config flow.
    name: str
    #: Model offered by default in the config flow.
    default_model: str

    def __init__(self, hass: HomeAssistant, api_key: str, model: str) -> None:
        self.hass = hass
        self._api_key = api_key
        self.model = model

    @classmethod
    @abstractmethod
    def suggested_models(cls) -> list[str]:
        """Models offered in the config flow dropdown (custom values allowed)."""

    @abstractmethod
    async def async_validate(self) -> None:
        """Make a cheap authenticated call. Raise ProviderAuthError / ProviderError."""

    @abstractmethod
    async def async_extract_from_image(self, image: bytes, mime_type: str) -> Extraction:
        """Extract ingredients from one image held in memory."""

    @abstractmethod
    async def async_extract_from_text(self, text: str) -> Extraction:
        """Extract ingredients from page text scraped from a web page."""

    @abstractmethod
    async def async_categorize(self, names: list[str]) -> list[str]:
        """Return the shop section of each shopping-list item, in the same order."""
