from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.shopify_client import ShopifyClient
from app.core.config import Settings
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError


@pytest.mark.parametrize("first", [429, 503, "throttled", "timeout"])
async def test_browsing_retries_transient_only(monkeypatch, first):
    count = 0

    async def post(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            if first == "timeout":
                raise httpx.ReadTimeout("private upstream details")
            if first == "throttled":
                return httpx.Response(200, json={"errors": [{"message": "rate", "extensions": {"code": "THROTTLED"}}],
                    "extensions": {"cost": {"requestedQueryCost": 100, "throttleStatus": {"currentlyAvailable": 0, "restoreRate": 100}}}})
            return httpx.Response(first, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"data": {"menu": {"id": "ok"}}})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep)
    client = ShopifyClient(Settings("test.myshopify.com", "", "", shopify_access_token="private"))
    assert await client.query_with_retry("query { menu { id } }") == {"menu": {"id": "ok"}}
    assert count == 2 and sleep.await_count == 1


@pytest.mark.parametrize("status,body,error", [
    (403, {}, ShopifyAuthenticationError),
    (200, {"errors": [{"message": "Access denied", "extensions": {"code": "ACCESS_DENIED"}}]}, ShopifyAPIError),
    (400, {}, ShopifyAPIError),
])
async def test_browsing_does_not_retry_permission_or_query_errors(monkeypatch, status, body, error):
    post = AsyncMock(return_value=httpx.Response(status, json=body))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    client = ShopifyClient(Settings("test.myshopify.com", "", "", shopify_access_token="private"))
    with pytest.raises(error):
        await client.query_with_retry("query { menu { id } }")
    assert post.await_count == 1


async def test_retry_is_bounded(monkeypatch):
    post = AsyncMock(return_value=httpx.Response(503))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    client = ShopifyClient(Settings("test.myshopify.com", "", "", shopify_access_token="private"))
    with pytest.raises(ShopifyAPIError):
        await client.query_with_retry("query { menu { id } }")
    assert post.await_count == 3


async def test_existing_query_does_not_retry(monkeypatch):
    post = AsyncMock(return_value=httpx.Response(503))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    client = ShopifyClient(Settings("test.myshopify.com", "", "", shopify_access_token="private"))
    with pytest.raises(ShopifyAPIError):
        await client.query("query { shop { name } }")
    assert post.await_count == 1


async def test_long_retry_after_fails_without_retrying_early(monkeypatch):
    post = AsyncMock(return_value=httpx.Response(429, headers={"Retry-After": "30"}))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    sleep = AsyncMock(); monkeypatch.setattr("asyncio.sleep", sleep)
    client = ShopifyClient(Settings("test.myshopify.com", "", "", shopify_access_token="private"))
    with pytest.raises(ShopifyAPIError):
        await client.query_with_retry("query { shop { name } }")
    assert post.await_count == 1 and not sleep.called
