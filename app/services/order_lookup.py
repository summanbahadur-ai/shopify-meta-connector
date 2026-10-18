"""Filtered order discovery and complete detail retrieval, independent of HTTP."""

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.clients import order_queries as queries
from app.core.exceptions import AmbiguousOrderError, OrderLookupLimitError, ShopifyAPIError
from app.messaging.order_formatter import format_order_status
from app.schemas.order_status import OrderLookup, email_forms, normalize_phone


class GraphQLClient(Protocol):
    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]: ...


def search_value(value: str) -> str:
    """Quote Shopify search literals; GraphQL variables alone do not escape search syntax."""
    for character in ("\\", '"', ":", "(", ")"):
        value = value.replace(character, "\\" + character)
    return f'"{value}"'


class OrderLookupService:
    # Bound work per lookup rather than running unbounded scans in a Worker.
    MAX_REQUESTS = 60
    MAX_PAGES = 20

    def __init__(self, client: GraphQLClient):
        self.client = client
        self._requests = 0

    async def _query(self, document: str, variables: dict) -> dict:
        if self._requests >= self.MAX_REQUESTS:
            raise OrderLookupLimitError("Order lookup exceeded its work limit. Please try again or contact support.")
        self._requests += 1
        return await self.client.query(document, variables)

    async def _pages(self, document: str, variables: dict, path: tuple[str, ...],
                     initial: dict | None = None) -> AsyncIterator[dict]:
        after = None
        seen: set[str] = set()
        for page_number in range(self.MAX_PAGES):
            if page_number == 0 and initial is not None:
                page = initial
            else:
                data = await self._query(document, {**variables, "after": after})
                try:
                    for key in path:
                        data = data[key]
                    page = data
                except (KeyError, TypeError) as exc:
                    raise ShopifyAPIError("Shopify returned incomplete order lookup data") from exc
            if not isinstance(page, dict) or not isinstance(page.get("nodes"), list):
                raise ShopifyAPIError("Shopify returned an invalid order lookup page")
            info = page.get("pageInfo")
            if not isinstance(info, dict) or not isinstance(info.get("hasNextPage"), bool):
                raise ShopifyAPIError("Shopify returned invalid order pagination")
            # Validate continuation before yielding; no false uniqueness on broken pages.
            cursor = info.get("endCursor")
            if info["hasNextPage"] and (not cursor or cursor in seen):
                raise ShopifyAPIError("Shopify returned invalid order pagination")
            for node in page["nodes"]:
                yield node
            if not info["hasNextPage"]:
                return
            seen.add(cursor)
            after = cursor
        raise OrderLookupLimitError("Order lookup exceeded its work limit. Please try again or contact support.")

    async def get_status(self, lookup: OrderLookup) -> dict | None:
        # A service instance may be reused, so the per-lookup budget is isolated.
        worker = OrderLookupService(self.client)
        return await worker._get_status(lookup)

    @staticmethod
    def _matches(order: dict, lookup: OrderLookup) -> bool:
        if order.get("name") != lookup.order_number:
            return False
        email = order.get("email")
        if not isinstance(email, str):
            return False
        try:
            if email_forms(email)[0] != lookup.email:
                return False
        except ValueError:
            return False
        if lookup.phone is not None:
            phone = order.get("phone")
            if not isinstance(phone, str):
                return False
            try:
                if normalize_phone(phone) != lookup.phone:
                    return False
            except ValueError:
                return False
        return True

    async def _get_status(self, lookup: OrderLookup) -> dict | None:
        email_filters = [f"email:{search_value(value)}" for value in email_forms(lookup.email)]
        email_filter = email_filters[0] if len(email_filters) == 1 else f"({' OR '.join(email_filters)})"
        search = f"name:{search_value(lookup.order_number)} AND {email_filter}"
        include_phone = lookup.phone is not None
        matches: dict[str, dict] = {}
        async for order in self._pages(queries.ORDER_LOOKUP,
                {"first": 50, "query": search, "includePhone": include_phone}, ("orders",)):
            if self._matches(order, lookup):
                matches[order["id"]] = order
                if len(matches) > 1:
                    raise AmbiguousOrderError(
                        "Multiple orders match this order number. Please contact support.")
        if not matches:
            return None
        identifier = next(iter(matches))
        data = await self._query(queries.ORDER_STATUS_DETAILS,
                                 {"id": identifier, "includePhone": include_phone})
        order = data.get("order")
        if order is None:
            return None
        # Contacts can change between discovery and detail retrieval; fail closed.
        if not self._matches(order, lookup):
            return None
        try:
            order["lineItems"]["nodes"] = [node async for node in self._pages(
                queries.ORDER_ITEMS, {"id": identifier}, ("order", "lineItems"), order["lineItems"])]
            for shipment in order["fulfillments"]:
                shipment["fulfillmentLineItems"]["nodes"] = [node async for node in self._pages(
                    queries.FULFILLMENT_ITEMS, {"id": shipment["id"]},
                    ("fulfillment", "fulfillmentLineItems"), shipment["fulfillmentLineItems"])]
            return format_order_status(order)
        except (KeyError, TypeError, ValueError) as exc:
            raise ShopifyAPIError("Shopify returned incomplete order status data") from exc
