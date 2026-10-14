# Order-status service contract

Status: Implemented. This describes the current code. Deployment and live-store
verification are separate from the mocked tests.

## Purpose

Find one order using its required order number and return structured facts plus a
customer-friendly message for a future WhatsApp integration. No LLM is used.
There is no public endpoint for listing orders.

## Implementation files

| Responsibility | File |
| --- | --- |
| HTTP endpoint and validation dependency | `app/api/v1/shopify.py` |
| Validated input and public response models | `app/schemas/order_status.py` |
| Existing service entry point | `app/services/shopify_service.py` |
| Filtered discovery, exact matching, pagination | `app/services/order_lookup.py` |
| Shopify GraphQL documents | `app/clients/order_queries.py` |
| Shopify authentication/transport | `app/clients/shopify_client.py` |
| Status mappings and natural-language templates | `app/messaging/order_messages.py` |
| Status derivation and message formatting | `app/messaging/order_formatter.py` |
| HTTP error translation | `app/main.py` |
| Regression tests | `tests/test_order_lookup.py` |

Read [shared.md](shared.md) for credentials, HTTP transport, and upstream errors.

## Input

GET `/api/v1/shopify/orders/status?order_number=1001`.

`order_number` is the only supported lookup input and is mandatory. It accepts
an order's displayed name, up to 128 characters. Numeric `1001` becomes `#1001`;
custom store prefixes/suffixes are preserved. Surrounding whitespace is trimmed.
Missing/blank names, `#` alone, control characters, and overlong names return 422
before loading Shopify settings or making any Shopify call.

Use `%23` for a literal `#` in a URL, or let your HTTP client encode parameters.

Internal interface:

```python
await ShopifyService(client).get_order_status(order_number="1001")
```

Returns the response dictionary below, or `None` for no match. Invalid supplied
service inputs raise Pydantic `ValidationError`; omitting the required Python
argument raises `TypeError`.

## External API calls

All calls POST GraphQL through the shared Shopify client to
`https://{store}/admin/api/{version}/graphql.json` (configured version `2026-07`).
The API's internal order searches remain filtered; they are not publicly exposed.

1. `OrderLookup` queries `orders` using the quoted, escaped name filter
   `name:"#1001"`. Variables: `first=50`, `after=<cursor or null>`, `query=<filter>`.
   Search escaping is separate from GraphQL parameterization. No unfiltered order
   query or customer lookup is made.
2. Verify that each returned name exactly equals the normalized order number.
   Follow filtered pages to establish uniqueness and deduplicate IDs. If different
   orders share the same exact name, return 409 asking the caller to contact support.
3. For the unique order, `OrderStatusDetails(id)` fetches items and fulfillments.
   `OrderItems(id, after)` and `FulfillmentItems(id, after)` fetch further item
   pages as needed. Item page size is 100. Fulfillments/tracking arrays are requested
   without a truncating `first` argument.

## Upstream response fields

- `OrderLookup`: `orders.nodes` contains only `id` and `name`;
  `orders.pageInfo` contains `hasNextPage` and `endCursor`.
- `OrderStatusDetails`: `order` contains `id`, `name`, `cancelledAt`,
  `displayFinancialStatus`, `displayFulfillmentStatus`, `lineItems`, `fulfillments`.
- `lineItems.nodes`: `id`, `title`, `quantity`, `currentQuantity`, `requiresShipping`;
  `pageInfo` is included. Current quantities exclude refunded/removed units;
  zero-current-quantity lines are omitted from the public items list.
- Each fulfillment: `id`, `status`, `displayStatus`, `requiresShipping`,
  `deliveredAt`, `inTransitAt`, `trackingInfo { company number url }`, and
  `fulfillmentLineItems { nodes { quantity lineItem { id title } } pageInfo }`.

## Returned result

Success is HTTP 200 with the same dictionary returned by the service:

```json
{
  "message": "Your order #1001 containing 1 Blue Shirt has shipped.\nShipment 1: 1 Blue Shirt has shipped.\nTracking number: TRACK123 (Example Carrier).\nTrack it here: https://example.com/track/TRACK123",
  "order_number": "#1001",
  "status": "shipped",
  "items": [{"title": "Blue Shirt", "quantity": 1}],
  "remaining_items": [],
  "shipments": [{
    "status": "shipped",
    "items": [{"title": "Blue Shirt", "quantity": 1}],
    "tracking": [{
      "company": "Example Carrier",
      "number": "TRACK123",
      "url": "https://example.com/track/TRACK123"
    }]
  }]
}
```

Customer email, phone, address, and Shopify IDs are not returned. Shipments retain
separate item/quantity lists and tracking records. Tracking fields can be null;
unsafe non-HTTP(S) URLs are omitted. Empty tracking produces an empty list.
`remaining_items` means physical quantities not yet evidenced as shipped; it does
not imply items are still awaiting fulfillment or payment (e.g. pickup/cancellation).
An order with no active items has `items: []` and no item phrase in the header.
No matching order returns 404, not an empty successful result.

## Natural-language rules

Templates and Shopify keyword mappings live in `order_messages.py`. Add or change
copy there; keep selection/quantity logic in `order_formatter.py`. Templates use
named placeholders and deterministic English. The formatter returns facts as well
as text so a WhatsApp handler does not need to parse the message.

Priority: cancelled order; delivery issue; complete delivered coverage; complete
out-for-delivery/delivered coverage; complete shipped coverage; partial shipped
coverage; fulfillment/payment/hold/scheduled state; otherwise processing.

- Shipment movement uses Shopify display status or actual transit/delivery
  timestamps. Tracking-label creation alone does not prove shipment.
- Carrier pickup means shipped. Attempted delivery, delayed, not-delivered, and
  failed states take precedence over historical transit timestamps.
- Fulfilled and marked-as-fulfilled mean fulfilled, not shipped/delivered.
- Unknown shipment states fall back to processing rather than inventing delivery.
- Cancelled fulfillments do not contribute to shipped/delivered quantity totals.
- Full shipped/delivered coverage is checked per physical line-item ID and quantity;
  partial shipment messages identify the remaining physical quantities.
- For mixed digital/physical orders, movement messages explicitly describe only
  physical items. The structured items list still includes digital items.
- Pickup status appears on the relevant shipment and is not described as shipping.
- Cancelled order messages omit shipment/tracking prose.
- Missing tracking says information is not yet available for moving shipments;
  never invent tracking numbers, URLs, delivery dates, or product details.

Public order states: `processing`, `awaiting_payment`, `cancelled`, `on_hold`,
`scheduled`, `fulfilled`, `partially_fulfilled`, `partially_shipped`, `shipped`,
`out_for_delivery`, `delivered`, `delivery_exception`. Shipment states additionally
include `ready_for_pickup` and `picked_up`.

## Errors and work limits

| Condition | HTTP response |
| --- | --- |
| Missing, blank, or invalid supplied inputs | 422 with field validation details, without echoing supplied values |
| No match in accessible history | 404 with a history-aware message |
| Multiple exact matches | 409 asking the caller to contact support; no matched-order details |
| Lookup exceeds budget | 503 asking the caller to retry or contact support; no partial result |
| Missing/repeated continuation cursor or incomplete detail data | 502 |
| Authentication or upstream Shopify failure | Shared 502 behavior |

Every connection allows at most 20 pages. A lookup allows at most 60 GraphQL
requests across order searches and item pagination. Limits fail explicitly
rather than returning truncated data. Request budgets are isolated per lookup.

## Shopify access and integration limits

Requires `read_orders`. This lookup does not query customer profiles, email,
phone, or addresses and does not require `read_customers` for its search.
Default order access is the last 60 days; older orders require `read_all_orders`
approval/access. A no-match does not prove an order never existed outside the
accessible history window.

The HTTP endpoint currently has no caller authentication. Restrict access to a
trusted backend until the WhatsApp integration verifies customer/order ownership.
Syntax validation and knowledge of an order number are not proof of ownership.

## Verification

`tests/test_order_lookup.py` covers route removal, validation before settings or
Shopify calls, required order number, normalization/escaping, exact matching, duplicate names on
later pages, order pagination/deduplication, no match, request budget,
broken pagination, item pagination, message-copy extension, processing/payment,
cancellation, split shipments and remaining quantities, tracking, mixed digital
items, explicit fulfillment, carrier pickup, and delivery exceptions.

Run `uv run pytest -q`. Tests mock the external GraphQL boundary; they do not
verify live Shopify permissions or replace a Cloudflare packaging check.

## Official references

- [Orders filters](https://shopify.dev/docs/api/admin-graphql/2026-07/queries/orders)
- [Order fields and access](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Order)
- [Fulfillment fields](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Fulfillment)
- [Fulfillment status keywords](https://shopify.dev/docs/api/admin-graphql/2026-07/enums/FulfillmentDisplayStatus)
