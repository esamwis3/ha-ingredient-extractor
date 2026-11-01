"""Constants for the Ingredient Extractor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ingredient_extractor"

CONF_PROVIDER: Final = "provider"
CONF_MODEL: Final = "model"
CONF_TODO_ENTITY: Final = "todo_entity"
CONF_SHARE_ENABLED: Final = "share_enabled"
CONF_SHARE_ENABLED: Final = "share_enabled"

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

# Web page fetching (recipe links).
FETCH_TIMEOUT_SECONDS: Final = 15
MAX_PAGE_BYTES: Final = 3 * 1024 * 1024
MAX_PAGE_TEXT_CHARS: Final = 15_000
MAX_REDIRECTS: Final = 5

# Event fired by the Android Companion app's share sheet.
EVENT_MOBILE_APP_SHARE: Final = "mobile_app.share"

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
ERR_INVALID_URL: Final = "invalid_url"
ERR_BLOCKED_URL: Final = "blocked_url"
ERR_FETCH_FAILED: Final = "fetch_failed"
