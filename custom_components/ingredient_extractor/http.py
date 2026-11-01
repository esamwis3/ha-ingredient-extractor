"""HTTP endpoint the card uploads recipe photos to."""

from __future__ import annotations

import logging
import time
from http import HTTPStatus
from typing import Any

from aiohttp import BodyPartReader, ClientError, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import (
    API_EXTRACT_URL,
    DOMAIN,
    ERR_NO_IMAGE,
    ERR_NO_INGREDIENTS,
    ERR_NOT_A_RECIPE,
    ERR_NOT_CONFIGURED,
    ERR_PROVIDER,
    ERR_PROVIDER_AUTH,
    ERR_TIMEOUT,
    ERR_TODO,
    ERR_TOO_LARGE,
    ERR_UNSUPPORTED_TYPE,
    MAX_IMAGE_BYTES,
    MAX_REQUEST_BYTES,
)
from .extractor import (
    NoIngredientsError,
    NotARecipeError,
    TodoAddError,
    async_extract_and_add,
)
from .providers.base import ProviderAuthError, ProviderError, ProviderTimeoutError

_LOGGER = logging.getLogger(__name__)

_CHUNK = 64 * 1024


def sniff_image_type(data: bytes) -> str | None:
    """Detect the MIME type from magic bytes; the client's claim is ignored."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return None


def _error(
    status: HTTPStatus, code: str, message: str, items: list[str] | None = None
) -> web.Response:
    body: dict[str, Any] = {"ok": False, "error": code, "message": message}
    if items:
        body["items"] = items
    return web.json_response(body, status=status)


class _TooLarge(Exception):
    """Upload exceeded MAX_IMAGE_BYTES."""


async def _read_image(request: web.Request) -> bytes | None:
    """Stream the `image` part into memory, aborting past the size cap."""
    try:
        reader = await request.multipart()
        while (part := await reader.next()) is not None:
            if not isinstance(part, BodyPartReader) or part.name != "image":
                continue
            buf = bytearray()
            while chunk := await part.read_chunk(_CHUNK):
                buf += chunk
                if len(buf) > MAX_IMAGE_BYTES:
                    raise _TooLarge
            return bytes(buf)
    except (ValueError, AssertionError, ClientError):
        return None
    return None


class IngredientExtractView(HomeAssistantView):
    """POST a recipe photo, get ingredients added to the todo list."""

    url = API_EXTRACT_URL
    name = "api:ingredient_extractor:extract"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Handle an upload."""
        request._client_max_size = MAX_REQUEST_BYTES  # noqa: SLF001
        too_large = _error(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            ERR_TOO_LARGE,
            "That image is too large (5 MB maximum)",
        )
        if (request.content_length or 0) > MAX_REQUEST_BYTES:
            return too_large

        hass = request.app[KEY_HASS]
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return _error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ERR_NOT_CONFIGURED,
                "Ingredient Extractor is not set up",
            )
        runtime = entries[0].runtime_data

        image: bytes | None = None
        try:
            try:
                image = await _read_image(request)
            except _TooLarge:
                return too_large
            if not image:
                return _error(
                    HTTPStatus.BAD_REQUEST, ERR_NO_IMAGE, "No image was uploaded"
                )
            mime = sniff_image_type(image)
            if mime is None:
                return _error(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    ERR_UNSUPPORTED_TYPE,
                    "Unsupported image type; use JPEG, PNG, WebP or GIF",
                )

            started = time.monotonic()
            _LOGGER.debug("Extracting from %s image, %d bytes", mime, len(image))
            try:
                items = await async_extract_and_add(
                    hass,
                    runtime.provider,
                    runtime.todo_entity,
                    image,
                    mime,
                    runtime.lock,
                )
            except NotARecipeError:
                return _error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    ERR_NOT_A_RECIPE,
                    "That doesn't look like a recipe",
                )
            except NoIngredientsError:
                return _error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    ERR_NO_INGREDIENTS,
                    "No ingredients could be read from that image",
                )
            except ProviderAuthError as err:
                return _error(HTTPStatus.BAD_GATEWAY, ERR_PROVIDER_AUTH, str(err))
            except ProviderTimeoutError as err:
                return _error(HTTPStatus.GATEWAY_TIMEOUT, ERR_TIMEOUT, str(err))
            except ProviderError as err:
                return _error(HTTPStatus.BAD_GATEWAY, ERR_PROVIDER, str(err))
            except TodoAddError as err:
                return _error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    ERR_TODO,
                    "Could not add items to the todo list",
                    err.added,
                )

            duration_ms = round((time.monotonic() - started) * 1000)
            _LOGGER.debug("Added %d items in %d ms", len(items), duration_ms)
            return web.json_response(
                {
                    "ok": True,
                    "items": items,
                    "added": len(items),
                    "todo_entity": runtime.todo_entity,
                    "duration_ms": duration_ms,
                }
            )
        finally:
            del image
