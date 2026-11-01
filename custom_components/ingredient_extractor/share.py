"""Handle links shared from the Android Companion app (`mobile_app.share`)."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import Event, HomeAssistant
from homeassistant.util import slugify

from .extractor import async_extract_url_and_add
from .http import EXTRACT_ERRORS, describe_extract_error

_LOGGER = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TITLE = "Shopping list"


def first_url(data: dict[str, Any]) -> str | None:
    """Return the first http(s) URL in the event's `url` or `text`."""
    for key in ("url", "text"):
        value = data.get(key)
        if isinstance(value, str) and (match := _URL_RE.search(value)):
            return match.group(0).rstrip(".,;)")
    return None


def notify_services(hass: HomeAssistant, user_id: str | None) -> list[str]:
    """Notify service names for the user's Android app registrations."""
    if not user_id:
        return []
    names: list[str] = []
    for entry in hass.config_entries.async_entries("mobile_app"):
        if entry.data.get("user_id") != user_id:
            continue
        if str(entry.data.get("os_name", "")).lower() != "android":
            continue
        name = f"mobile_app_{slugify(str(entry.data.get('device_name', '')))}"
        if name not in names and hass.services.has_service("notify", name):
            names.append(name)
    return names


async def async_notify(hass: HomeAssistant, user_id: str | None, message: str) -> None:
    """Tell the sharing user's phone, or fall back to a persistent notification."""
    if services := notify_services(hass, user_id):
        for service in services:
            await hass.services.async_call(
                "notify", service, {"title": _TITLE, "message": message}, blocking=True
            )
    else:
        persistent_notification.async_create(
            hass, message, title=_TITLE, notification_id="ingredient_extractor_share"
        )


async def async_handle_share(hass: HomeAssistant, entry: Any, event: Event) -> None:
    """Extract the shared link and report the outcome. Never logs page content."""
    url = first_url(event.data)
    if url is None:
        return
    runtime = entry.runtime_data
    try:
        items, title = await async_extract_url_and_add(
            hass, runtime.provider, runtime.todo_entity, url, runtime.lock
        )
        count = f"{len(items)} item{'' if len(items) == 1 else 's'}"
        message = (
            f"Added {count} from {title}" if title else f"Added {count} to your shopping list"
        )
    except EXTRACT_ERRORS as err:
        message = (describe_extract_error(err, "page") or (0, "", "Something went wrong"))[2]
        _LOGGER.debug("Shared link failed: %s", type(err).__name__)
    await async_notify(hass, event.context.user_id, message)
