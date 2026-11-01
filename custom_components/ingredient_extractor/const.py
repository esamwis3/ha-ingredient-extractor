"""Constants for the Ingredient Extractor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ingredient_extractor"

CONF_PROVIDER: Final = "provider"
CONF_MODEL: Final = "model"
CONF_TODO_ENTITY: Final = "todo_entity"

DEFAULT_PROVIDER: Final = "anthropic"
DEFAULT_TODO_ENTITY: Final = "todo.shopping_list"

# HTTP API used by the card. GET-free, POST only, auth required.
API_EXTRACT_URL: Final = "/api/ingredient_extractor/extract"

# Static URL the bundled card is served from.
CARD_FILENAME: Final = "ingredient-extractor-card.js"
CARD_URL_BASE: Final = "/ingredient_extractor_static"

# Image limits. The card resizes before upload, so these are a backstop.
MAX_IMAGE_BYTES: Final = 5 * 1024 * 1024  # Anthropic per-image limit
MAX_REQUEST_BYTES: Final = 8 * 1024 * 1024  # multipart overhead headroom
ALLOWED_IMAGE_TYPES: Final = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)

EXTRACT_TIMEOUT_SECONDS: Final = 45
MAX_INGREDIENTS: Final = 60

# Error codes returned to the card (`{"ok": false, "error": <code>, "message": ...}`).
ERR_NO_IMAGE: Final = "no_image"
ERR_TOO_LARGE: Final = "too_large"
ERR_UNSUPPORTED_TYPE: Final = "unsupported_type"
ERR_NOT_A_RECIPE: Final = "not_a_recipe"
ERR_NO_INGREDIENTS: Final = "no_ingredients"
ERR_PROVIDER_AUTH: Final = "provider_auth"
ERR_TIMEOUT: Final = "timeout"
ERR_PROVIDER: Final = "provider_error"
ERR_TODO: Final = "todo_error"
ERR_NOT_CONFIGURED: Final = "not_configured"
