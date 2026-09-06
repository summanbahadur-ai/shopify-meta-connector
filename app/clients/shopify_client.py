from __future__ import annotations

import time
from typing import Any
import httpx

from app.core.config import Settings
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class ShopifyClient:
    def __init__(self, settings: Settings, timeout: float = 20.0):
        self.settings = settings
        self.timeout = timeout

    async def _access_token(self) -> str:
        if self.settings.shopify_access_token:
            return self.settings.shopify_access_token

        cached = _TOKEN_CACHE.get(self.settings.shopify_store_domain)
        now = time.time()
        if cached and cached[1] > now + 60:
            return cached[0]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.settings.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.settings.shopify_client_id,
                        "client_secret": self.settings.shopify_client_secret,
                    },
                )
        except httpx.HTTPError as exc:
            raise ShopifyAuthenticationError(f"Unable to obtain Shopify access token: {exc}") from exc

        if response.status_code >= 400:
            raise ShopifyAuthenticationError(f"Shopify token request failed with HTTP {response.status_code}")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ShopifyAuthenticationError("Shopify token response did not contain access_token")
        expires_in = int(payload.get("expires_in", 86399))
        _TOKEN_CACHE[self.settings.shopify_store_domain] = (token, now + expires_in)
        return token

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._access_token()
        headers = {"Content-Type": "application/json", "X-Shopify-Access-Token": token}
        payload = {"query": query, "variables": variables or {}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.settings.graphql_url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ShopifyAPIError(f"Unable to reach Shopify: {exc}") from exc

        if response.status_code in (401, 403):
            _TOKEN_CACHE.pop(self.settings.shopify_store_domain, None)
            raise ShopifyAuthenticationError("Shopify rejected the token or configured app scopes")
        if response.status_code >= 400:
            raise ShopifyAPIError(f"Shopify returned HTTP {response.status_code}: {response.text[:500]}")

        data = response.json()
        if data.get("errors"):
            messages = "; ".join(str(item.get("message", item)) for item in data["errors"])
            raise ShopifyAPIError(messages)
        return data.get("data", {})
