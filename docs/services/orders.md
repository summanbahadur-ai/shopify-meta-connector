# Orders and order status

## Purpose and implementation

Read orders and find a single order by its displayed number.
Routes: `app/api/v1/shopify.py`. Methods and `ORDERS_QUERY`:
`app/services/shopify_service.py`. Shared calls/errors: [shared.md](shared.md).
Existing basic listing test: `tests/test_shopify_service.py::test_orders`.

## List orders

GET `/api/v1/shopify/orders` -> `get_orders(limit=20, after=None, query=None)`.

| Query input | Default | Rule |
| --- | --- | --- |
| `limit` | 20 | Integer 1..100; HTTP rejects outside range with 422 |
| `after` | null | Optional Shopify cursor |
| `query` | null | Optional Shopify search string, forwarded unchanged |

Direct service calls clamp limit to 1..100. Calls Shopify GraphQL `Orders`
with variables `{"first": limit, "after": after, "query": query}`. Query uses
`sortKey: CREATED_AT, reverse: true` (newest created first).
Upstream inner data has `orders.nodes` and `orders.pageInfo`. Selected fields:

```text
id name createdAt processedAt cancelledAt
displayFinancialStatus displayFulfillmentStatus
```

Service and HTTP 200 response:

```json
{
  "count": 1,
  "orders": [{
    "id": "gid://shopify/Order/1",
    "name": "#1001",
    "createdAt": "2026-10-01T12:00:00Z",
    "processedAt": "2026-10-01T12:00:00Z",
    "cancelledAt": null,
    "displayFinancialStatus": "PAID",
    "displayFulfillmentStatus": "FULFILLED"
  }],
  "page_info": {"hasNextPage": false, "endCursor": null}
}
```

`count` is this page's size. Empty results return count 0 and orders [].

## Look up status

GET `/api/v1/shopify/orders/status?order_number=1001` ->
`get_order_status(order_number: str)`.

- `order_number` is required; omission returns 422.
- Strip whitespace and prepend `#` if absent. No further format/empty-string
  validation is implemented. Encode `#` as `%23` if putting it in the URL.
- Call `get_orders(limit=10, query="name:#1001")` after normalization.
- Scan the returned orders for an exact `name` match.
- Return the first matching order object, with the fields shown above.
- Service returns `None` if absent; the HTTP route returns 404
  `{"detail": "Order not found"}`. It does not search additional pages.

Both operations can produce the shared upstream errors. There is currently
no customer/order ownership verification. These endpoints should not become
customer-facing order lookups without adding appropriate authorization.

## Acceptance checks for changes

Check query forwarding, limits/cursors, whitespace and # normalization, exact
matching, no-match 404, and authorization if exposing this to customers.
Existing tests do not cover status lookup or its 404 behavior.

## Requested change

None pending.
