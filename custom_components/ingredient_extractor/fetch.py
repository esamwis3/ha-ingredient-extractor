"""Fetch a recipe web page safely and reduce it to text a model can read."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser
import html
import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

from aiohttp import ClientError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    FETCH_TIMEOUT_SECONDS,
    MAX_PAGE_BYTES,
    MAX_PAGE_TEXT_CHARS,
    MAX_REDIRECTS,
)

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
_SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header", "svg"})
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


class InvalidUrlError(Exception):
    """The URL is malformed or not http(s)."""


class BlockedUrlError(Exception):
    """The URL points at a non-public address."""


class FetchError(Exception):
    """The page could not be retrieved. The message is safe to show a user."""


@dataclass(frozen=True, slots=True)
class RecipePage:
    """A fetched page reduced to model input."""

    title: str | None
    text: str
    #: True when `text` came from schema.org Recipe data rather than page text.
    structured: bool


def _clean(value: Any) -> str:
    """Strip tags and entities and collapse whitespace."""
    return _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", str(value)))).strip()


class _PageParser(HTMLParser):
    """Collect JSON-LD blocks, titles and visible text in one pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.title: str | None = None
        self.og_title: str | None = None
        self.parts: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_ld = False
        self._ld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:title" and a.get("content"):
            self.og_title = a["content"]
        elif tag == "script" and "ld+json" in (a.get("type") or "").lower():
            self._in_ld, self._ld_buf = True, []
        elif tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self.json_ld.append("".join(self._ld_buf))
            self._in_ld = False
        elif tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_buf.append(data)
        elif self._in_title:
            self.title = (self.title or "") + data
        elif not self._skip:
            self.parts.append(data)


def _is_recipe(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(isinstance(k, str) and k.rsplit("/", 1)[-1] == "Recipe" for k in kinds)


def _find_recipe(node: Any) -> dict[str, Any] | None:
    """Depth-first search for a schema.org Recipe (lists, @graph, nesting)."""
    if isinstance(node, list):
        for child in node:
            if (found := _find_recipe(child)) is not None:
                return found
    elif isinstance(node, dict):
        if _is_recipe(node):
            return node
        for key in ("@graph", "mainEntity", "mainEntityOfPage"):
            if (found := _find_recipe(node.get(key))) is not None:
                return found
    return None


def _structured_text(blocks: list[str]) -> tuple[str | None, str] | None:
    """Build the model input from the first JSON-LD Recipe with ingredients."""
    for block in blocks:
        try:
            recipe = _find_recipe(json.loads(block))
        except ValueError:
            continue
        if recipe is None:
            continue
        raw = recipe.get("recipeIngredient")
        raw = [raw] if isinstance(raw, str) else raw
        lines = [c for c in (_clean(x) for x in raw or [] if isinstance(x, str)) if c]
        if not lines:
            continue
        name = _clean(recipe["name"]) if isinstance(recipe.get("name"), str) else ""
        text = f"Recipe: {name}\nIngredients:\n" + "\n".join(f"- {x}" for x in lines)
        return (name or None), text
    return None


def parse_recipe_page(markup: str) -> RecipePage:
    """Reduce page HTML to a RecipePage."""
    parser = _PageParser()
    parser.feed(markup)
    parser.close()
    page_title = _clean(parser.og_title or parser.title or "") or None

    if (found := _structured_text(parser.json_ld)) is not None:
        return RecipePage(found[0] or page_title, found[1], True)
    text = _SPACE_RE.sub(" ", " ".join(parser.parts)).strip()
    return RecipePage(page_title, text[:MAX_PAGE_TEXT_CHARS], False)


def _check_scheme(url: str) -> str:
    """Return the hostname of a valid http(s) URL."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
    except ValueError:
        raise InvalidUrlError from None
    if parts.scheme not in ("http", "https") or not host:
        raise InvalidUrlError
    return host


async def _async_check_public(host: str) -> None:
    """Reject hosts that are, or resolve to, anything but public addresses."""
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        except OSError:
            raise FetchError("Couldn't open that page.") from None
        addrs = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos}
    for addr in addrs:
        # Unwrap ::ffff:a.b.c.d so a mapped private address can't slip through.
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        if not addr.is_global or addr.is_multicast:
            raise BlockedUrlError


async def _async_read_limited(resp: Any) -> bytes:
    """Read the body, aborting once it exceeds MAX_PAGE_BYTES."""
    buf = bytearray()
    async for chunk in resp.content.iter_chunked(64 * 1024):
        buf += chunk
        if len(buf) > MAX_PAGE_BYTES:
            raise FetchError("That page is too large to read.")
    return bytes(buf)


async def _async_get(hass: HomeAssistant, url: str) -> str:
    """GET the page, validating every redirect hop; return decoded HTML."""
    session = async_get_clientsession(hass)
    for _ in range(MAX_REDIRECTS + 1):
        await _async_check_public(_check_scheme(url))
        async with session.get(url, headers=_HEADERS, allow_redirects=False) as resp:
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise FetchError("Couldn't open that page.")
                url = urljoin(url, location)
                continue
            if not 200 <= resp.status < 300:
                raise FetchError(f"Couldn't open that page (HTTP {resp.status}).")
            ctype = resp.headers.get("Content-Type", "text/html").lower()
            if "html" not in ctype:
                raise FetchError("That link isn't a web page.")
            declared = resp.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
                raise FetchError("That page is too large to read.")
            body = await _async_read_limited(resp)
            return body.decode(resp.charset or "utf-8", errors="replace")
    raise FetchError("That page redirected too many times.")


async def async_fetch_recipe(hass: HomeAssistant, url: str) -> RecipePage:
    """Download `url` and extract recipe text. Never logs page content."""
    _check_scheme(url)
    try:
        async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
            markup = await _async_get(hass, url)
    except TimeoutError:
        raise FetchError("Couldn't open that page (it took too long).") from None
    except (ClientError, LookupError, ValueError) as err:
        _LOGGER.debug("Fetch failed: %s", type(err).__name__)
        raise FetchError("Couldn't open that page.") from None
    return parse_recipe_page(markup)
