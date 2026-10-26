from __future__ import annotations

from typing import Any

from app.schemas.order_status import OrderLookup
from app.services.order_lookup import OrderLookupService
from app.messaging.policy_formatter import policy_html_to_text


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

    async def get_order_status(self, order_number: str, email: str,
                               phone: str | None = None) -> dict[str, Any] | None:
        lookup = OrderLookup(order_number=order_number, email=email, phone=phone)
        return await OrderLookupService(self.client).get_status(lookup)

    async def get_policies(self, policy_type: str | None = None) -> list[dict[str, Any]]:
        policies = (await self.client.query(POLICIES_QUERY))["shop"]["shopPolicies"]
        if policy_type is not None:
            policies = [policy for policy in policies if policy.get("type") == policy_type]
        return [{**policy, "body": policy_html_to_text(policy.get("body"))} for policy in policies]

    async def get_pages(self, limit: int = 50, after: str | None = None, query: str | None = None) -> dict[str, Any]:
        first = min(max(limit, 1), 100)
        connection = (await self.client.query(PAGES_QUERY, {"first": first, "after": after, "query": query}))["pages"]
        return {"count": len(connection["nodes"]), "pages": connection["nodes"], "page_info": connection["pageInfo"]}
