"""Tests for page fetching, parsing and the SSRF guard."""

import json
import socket
from unittest.mock import patch

import pytest

from custom_components.ingredient_extractor.fetch import (
    BlockedUrlError,
    FetchError,
    InvalidUrlError,
    async_fetch_recipe,
    parse_recipe_page,
)


def _page(ld: object | None = None, body: str = "<p>Hello</p>", head: str = "") -> str:
    script = (
        f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else ""
    )
    return f"<html><head>{head}{script}</head><body>{body}</body></html>"


def _resolver(mapping: dict[str, str]):
    async def fake(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], 0))]

    return fake


@pytest.fixture
def dns(hass):
    """Resolve example hosts to documentation addresses, internal.example to private."""
    mapping = {
        "example.com": "93.184.216.34",
        "internal.example": "10.20.30.40",
        "www.example.com": "93.184.216.34",
    }
    with patch.object(hass.loop, "getaddrinfo", _resolver(mapping)):
        yield mapping


def test_json_ld_recipe_plain() -> None:
    page = parse_recipe_page(
        _page(
            {
                "@type": "Recipe",
                "name": "Chicken &amp; Rice",
                "recipeIngredient": ["500g <b>chicken</b>", "1 onion &amp; garlic", ""],
            },
            head="<title>Ignored</title>",
        )
    )
    assert page.structured is True
    assert page.title == "Chicken & Rice"
    assert page.text == (
        "Recipe: Chicken & Rice\nIngredients:\n- 500g chicken\n- 1 onion & garlic"
    )


def test_json_ld_graph_and_type_list() -> None:
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": "Site"},
            {"@type": ["Thing", "Recipe"], "name": "Soup", "recipeIngredient": ["water"]},
        ],
    }
    page = parse_recipe_page(_page(ld))
    assert page.structured and page.title == "Soup" and "- water" in page.text


def test_json_ld_top_level_list() -> None:
    ld = [{"@type": "BreadcrumbList"}, {"@type": "Recipe", "recipeIngredient": ["2 eggs"]}]
    page = parse_recipe_page(_page(ld, head="<title>Egg page</title>"))
    assert page.structured and page.title == "Egg page" and "- 2 eggs" in page.text


def test_fallback_visible_text() -> None:
    markup = (
        "<html><head><title>Tasty</title><meta property='og:title' content='OG Tasty'>"
        "<style>x{}</style></head><body><nav>MENU</nav><header>HEAD</header>"
        "<h1>Pancakes</h1><p>2   eggs</p><script>evil()</script>"
        "<svg><text>ICON</text></svg><footer>FOOT</footer></body></html>"
    )
    page = parse_recipe_page(markup)
    assert page.structured is False
    assert page.title == "OG Tasty"
    assert page.text == "Pancakes 2 eggs"


def test_fallback_truncates_and_handles_bad_json() -> None:
    markup = '<title>T</title><script type="application/ld+json">{bad</script><p>' + "x " * 20000
    page = parse_recipe_page(markup)
    assert not page.structured and page.title == "T" and len(page.text) == 15000


async def test_fetch_ok(hass, aioclient_mock, dns) -> None:
    aioclient_mock.get(
        "https://example.com/r",
        text=_page({"@type": "Recipe", "name": "Soup", "recipeIngredient": ["water"]}),
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    page = await async_fetch_recipe(hass, "https://example.com/r")
    assert page.title == "Soup" and page.structured


@pytest.mark.parametrize("url", ["", "ftp://example.com/x", "https:///x", "not a url"])
async def test_invalid_url(hass, url) -> None:
    with pytest.raises(InvalidUrlError):
        await async_fetch_recipe(hass, url)


@pytest.mark.parametrize(
    "url",
    [
        "http://10.20.30.40/x",
        "http://127.0.0.1/",
        "http://172.16.5.4/",
        "http://169.254.169.254/latest",
        "http://[::1]/",
        "http://[::ffff:10.20.30.40]/",
        "http://0.0.0.0/",
        "http://internal.example/x",
    ],
)
async def test_private_hosts_blocked(hass, dns, url) -> None:
    with pytest.raises(BlockedUrlError):
        await async_fetch_recipe(hass, url)


async def test_redirect_to_private_blocked(hass, aioclient_mock, dns) -> None:
    aioclient_mock.get(
        "https://example.com/r", status=302, headers={"Location": "http://internal.example/admin"}
    )
    with pytest.raises(BlockedUrlError):
        await async_fetch_recipe(hass, "https://example.com/r")
    assert aioclient_mock.call_count == 1


async def test_redirect_followed_and_limited(hass, aioclient_mock, dns) -> None:
    aioclient_mock.get(
        "https://example.com/a", status=301, headers={"Location": "/b"}
    )
    aioclient_mock.get("https://example.com/b", text=_page(body="<p>ok</p>"))
    page = await async_fetch_recipe(hass, "https://example.com/a")
    assert page.text == "ok"

    aioclient_mock.clear_requests()
    aioclient_mock.get("https://example.com/loop", status=302, headers={"Location": "/loop"})
    with pytest.raises(FetchError, match="redirected"):
        await async_fetch_recipe(hass, "https://example.com/loop")


async def test_http_error_message(hass, aioclient_mock, dns) -> None:
    aioclient_mock.get("https://example.com/r", status=403)
    with pytest.raises(FetchError, match=r"\(HTTP 403\)"):
        await async_fetch_recipe(hass, "https://example.com/r")


async def test_non_html_and_too_large(hass, aioclient_mock, dns) -> None:
    aioclient_mock.get(
        "https://example.com/a.pdf", content=b"%PDF", headers={"Content-Type": "application/pdf"}
    )
    with pytest.raises(FetchError, match="isn't a web page"):
        await async_fetch_recipe(hass, "https://example.com/a.pdf")

    aioclient_mock.get(
        "https://example.com/big",
        content=b"a" * (3 * 1024 * 1024 + 1),
        headers={"Content-Type": "text/html"},
    )
    with pytest.raises(FetchError, match="too large"):
        await async_fetch_recipe(hass, "https://example.com/big")


async def test_network_error(hass, aioclient_mock, dns) -> None:
    import aiohttp

    aioclient_mock.get("https://example.com/r", exc=aiohttp.ClientError())
    with pytest.raises(FetchError):
        await async_fetch_recipe(hass, "https://example.com/r")
