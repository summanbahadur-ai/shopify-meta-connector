from __future__ import annotations

from typing import Any

from app.schemas.order_status import OrderLookup
from app.services.order_lookup import OrderLookupService


SHOP_QUERY = """
query ShopConnection {
  shop {
    name
    myshopifyDomain
    primaryDomain { host url }
    currencyCode
    timezoneAbbreviation
  }
}
"""

PRODUCTS_QUERY = """
query Products($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    nodes {
      id title handle descriptionHtml vendor productType status tags
      featuredMedia { preview { image { url altText } } }
      variants(first: 100) {
        nodes { id title sku barcode price compareAtPrice }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

POLICIES_QUERY = """
query Policies {
  shop {
    shopPolicies { id title type body url createdAt updatedAt }
  }
}
"""

PAGES_QUERY = """
query Pages($first: Int!, $after: String, $query: String) {
  pages(first: $first, after: $after, query: $query) {
    nodes { id title handle body bodySummary isPublished createdAt updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class ShopifyService:
    def __init__(self, client):
        self.client = client

    async def get_connection_status(self) -> dict[str, Any]:
        data = await self.client.query(SHOP_QUERY)
        return {"connected": True, "shop": data["shop"]}

    async def get_shop(self) -> dict[str, Any]:
        return (await self.client.query(SHOP_QUERY))["shop"]

    async def get_products(self, limit: int = 50, after: str | None = None) -> dict[str, Any]:
        first = min(max(limit, 1), 100)
        connection = (await self.client.query(PRODUCTS_QUERY, {"first": first, "after": after}))["products"]
        return {"count": len(connection["nodes"]), "products": connection["nodes"], "page_info": connection["pageInfo"]}

    async def get_all_products(self) -> list[dict[str, Any]]:
        products: list[dict[str, Any]] = []
        after = None
        while True:
            page = await self.get_products(limit=100, after=after)
            products.extend(page["products"])
            if not page["page_info"]["hasNextPage"]:
                return products
            after = page["page_info"]["endCursor"]

    async def get_order_status(self, order_number: str, email: str,
                               phone: str | None = None) -> dict[str, Any] | None:
        lookup = OrderLookup(order_number=order_number, email=email, phone=phone)
        return await OrderLookupService(self.client).get_status(lookup)

    async def get_policies(self) -> list[dict[str, Any]]:
        return (await self.client.query(POLICIES_QUERY))["shop"]["shopPolicies"]

    async def get_pages(self, limit: int = 50, after: str | None = None, query: str | None = None) -> dict[str, Any]:
        first = min(max(limit, 1), 100)
        connection = (await self.client.query(PAGES_QUERY, {"first": first, "after": after, "query": query}))["pages"]
        return {"count": len(connection["nodes"]), "pages": connection["nodes"], "page_info": connection["pageInfo"]}
