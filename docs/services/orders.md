# Order-status service contract

Status: Implemented. This describes the current code. Deployment and live-store
verification are separate from the mocked tests.

## Purpose

Find one order using its required order number and email address and return structured facts plus a
customer-friendly message for a future WhatsApp integration. No LLM is used.
There is no public endpoint for listing orders.

## Implementation files

| Responsibility | File |
| --- | --- |
| HTTP endpoint and validation dependency | `app/api/v1/shopify.py` |
| Safe order-only exception boundary | `app/api/order_errors.py` |
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

GET `/api/v1/shopify/orders/status`.

| Query field | Required | Validation and meaning |
| --- | --- | --- |
| `order_number` | Yes | Order's displayed name, up to 128 characters; numeric `1001` becomes `#1001`; store prefixes/suffixes are preserved |
| `email` | Yes | Valid email syntax, up to 254 characters; trimmed, normalized, and compared case-insensitively with the order's contact email; equivalent Unicode/punycode domain names are supported |
| `phone` | No | If provided, a valid international phone with country code; normalized to E.164 and matched to the order's contact phone |

Order number and email must both match the same order. A supplied phone is an
additional AND check, never an alternative to email. Phone is checked against
`Order.phone` only, not a customer-profile or shipping/billing-address phone. If
that field is absent or differs, supplying phone makes the lookup fail with 404.

Missing required fields, blank supplied values, control characters, `#` alone,
overlong order names, invalid email syntax, and invalid phones return a formatted
422 response before
loading Shopify settings or making Shopify calls. All fields are validated even
if the other supplied fields are valid. Phone input permits common separators,
e.g. `+1 (415) 555-2671`, but requires an explicit country code; no country is guessed.
Email validation uses `email-validator` without DNS checks, and phone validation
uses `phonenumberslite`. Format validation does not prove mailbox/phone ownership.

Examples:

```text
/api/v1/shopify/orders/status?order_number=1001&email=buyer%40example.com
/api/v1/shopify/orders/status?order_number=1001&email=buyer%40example.com&phone=%2B14155552671
```

Use an HTTP client's parameter encoding; literal `#`, `@`, and `+` must be encoded
when constructing URLs. Inputs and retrieved customer contact details are not
included in the successful public response.

Internal interface:

```python
await ShopifyService(client).get_order_status(
    order_number="1001", email="buyer@example.com", phone=None
)
```

Returns the response dictionary below, or `None` for no match. Invalid supplied
service inputs raise Pydantic `ValidationError`; omitting the required Python
argument raises `TypeError`.

## External API calls

All calls POST GraphQL through the shared Shopify client to
`https://{store}/admin/api/{version}/graphql.json` (configured version `2026-07`).
The API's internal order searches remain filtered; they are not publicly exposed.

1. `OrderLookup` queries `orders` using
   `name:"#1001" AND email:"buyer@example.com"`. Both values are quoted and escaped
   separately from GraphQL parameterization. Variables: `first=50`,
   `after=<cursor or null>`, `query=<filter>`, and `includePhone=<phone supplied>`.
   No unfiltered order query or customer lookup is made.
   For an international domain, the email filter groups its equivalent Unicode
   and ASCII-domain spellings with OR, still under AND with the order name.
   Both sides use the same canonical normalization for exact matching.
2. Verify exact normalized order name and email locally. If phone was supplied,
   normalize the returned order phone and require equality too. Null/redacted or
   mismatching required contact data never bypasses these checks.
3. Follow filtered pages to establish uniqueness and deduplicate IDs. If different
   orders match all supplied identifiers, return 409 asking the caller to contact support.
4. For the unique order, `OrderStatusDetails(id, includePhone)` fetches items and
   fulfillments. Recheck name/email/optional phone before returning details in case
   contact data changed between discovery and detail retrieval.
5. `OrderItems(id, after)` and `FulfillmentItems(id, after)` fetch further item
   pages as needed. Item page size is 100. Fulfillments/tracking arrays are requested
   without a truncating `first` argument. Phone fields use `@include` and are not
   requested when the phone input is omitted.

## Upstream response fields

- `OrderLookup`: `orders.nodes` contains `id`, `name`, `email`, and conditionally `phone`;
  `orders.pageInfo` contains `hasNextPage` and `endCursor`.
- `OrderStatusDetails`: `order` contains `id`, `name`, `email`, conditionally `phone`, `cancelledAt`,
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
  "success": true,
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
No matching order returns a formatted 404 message, not an empty successful result.

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

## Customer-friendly failure responses

The order route catches validation, settings, Shopify, and unexpected exceptions
in a dedicated try/except HTTP boundary. Technical exceptions, stack traces,
Shopify error payloads, configuration names, and supplied contact values are never
included in the order lookup response. Other endpoints retain their own behavior.
Internal service/client layers may still raise typed exceptions; the boundary
translates them before any response reaches the customer.

Messages and stable codes are defined in `LOOKUP_ERROR_MESSAGES` in
`app/messaging/order_messages.py`. HTTP status codes remain meaningful; the chatbot
should display `message` and branch on `success`/`code`, not parse exception text.

| Condition | HTTP | Code | Customer message |
| --- | --- | --- | --- |
| Order number missing | 422 | `missing_order_number` | Please enter your order number, for example #1001. |
| Email missing | 422 | `missing_email` | Please enter the email address you used when placing the order. |
| Order number invalid | 422 | `invalid_order_number` | Please enter a valid order number, for example #1001. |
| Email syntax invalid | 422 | `invalid_email` | Please enter a valid email address, for example name@example.com. |
| Supplied phone invalid | 422 | `invalid_phone` | Please enter a valid phone number including its country code, for example +14155552671. |
| No match, incorrect contact, or inaccessible history | 404 | `order_not_found` | We couldn't find an order matching those details. Please check your order number, the email used at checkout, and your phone number if provided, then try again. |
| Multiple exact matches | 409 | `multiple_orders` | More than one order matches those details. Please contact the store with your order number for help. |
| Work limit reached | 503 | `lookup_limit` | We couldn't complete your order lookup right now. Please try again shortly or contact the store for help. |
| Shopify access/API failure, including broken upstream pagination | 502 | `service_unavailable` | We couldn't check your order right now. Please try again shortly. |
| Configuration or unexpected failure | 500 | `service_unavailable` | We couldn't check your order right now. Please try again shortly. |

Example invalid email response:

```json
{
  "success": false,
  "code": "invalid_email",
  "message": "Please enter a valid email address, for example name@example.com.",
  "errors": [{
    "field": "email",
    "code": "invalid_email",
    "message": "Please enter a valid email address, for example name@example.com."
  }]
}
```

If several fields are invalid, `errors` contains all field issues and `message`
combines their curated messages. The top-level `code` is the first issue's code.
Non-validation failures use the same envelope with `errors: []`. A mismatch never
reveals whether the order exists or which contact field differs. A syntactically
valid custom order name can still return no match; validation cannot establish
whether a real order exists without querying Shopify.

The server logs only the exception class/category for internal/upstream failures,
without exception messages, query values, credentials, or tracebacks. The boundary
also covers settings failures that occur before the endpoint body and response
validation failures. It does not convert failures into fake successful order data.

## Work limits

Every connection allows at most 20 pages. A lookup allows at most 60 GraphQL
requests across order searches and item pagination. Limits fail explicitly
rather than returning truncated data. Request budgets are isolated per lookup.

## Shopify access and integration limits

Requires `read_orders`, plus access to the protected **Email** field and, for
requests supplying phone, the protected **Phone** field. `read_customers` is not
needed for this implementation: no `Customer` object is queried. There is no
`read_emails` or `read_phones` scope to add. `read_orders` alone does not override
Shopify's protected-field restrictions.

### Update the Shopify app permissions

1. Open the existing app in Shopify's **Dev Dashboard > Apps > your app > Versions**.
   Ensure its access scopes include `read_orders`; preserve the existing product
   and content scopes used by other services.
2. If you change scopes, create/release a new app version, then approve the new
   permissions for the installed store. Releasing a version alone does not grant
   new scopes to existing installations. Follow Shopify's install/update flow;
   do not uninstall the working app just to refresh permissions.
3. Check access to protected Email and Phone fields. For a public app, Shopify's
   documented path is **Partner Dashboard > Apps > your app > API access requests >
   Protected customer data access**. Request/select Email and Phone and explain
   that they are used to match an order-status lookup to the order's contacts.
   Follow the review requirements shown for your app. Development-store-only apps
   still select the fields but do not need a production review.
4. Shopify documents different access rules by app type: protected fields are
   available to custom-distribution apps; public apps require approval; legacy
   admin-created custom app access can depend on the store plan. If the public-app
   request screen is absent for a Dev Dashboard custom app, do not assume you need
   to create a public app or add `read_customers`. Check the app's distribution,
   granted scopes, and actual Email/Phone field access first.
5. After permission changes are granted, deploy this code through GitHub Actions
   and test a known matching order/email, then the optional phone. Client ID and
   Client Secret remain the same for the same app. The existing client-credentials
   flow obtains access tokens; do not replace GitHub Secrets with a temporary token.
   A fresh deployment also avoids reusing the old in-memory access-token cache.

Default order access is the last 60 days; older orders need `read_all_orders`
approval/access. This is independent of Email/Phone protected-field access.
A no-match does not prove the order never existed outside the accessible history.
Shopify GraphQL access errors use the safe `service_unavailable` 502 response; redacted null contact
fields cannot be verified and produce the same 404 as a nonmatching identifier.

The HTTP endpoint currently has no caller authentication. Restrict access to a
trusted backend until the WhatsApp integration verifies customer/order ownership.
Matching identifiers reduce accidental disclosure but do not prove email/phone
ownership. A customer-facing integration still needs a trusted identity check.

## Verification

`tests/test_order_lookup.py` covers route removal, validation before settings or
Shopify calls, required order number and email, optional phone validation, normalization/escaping,
exact contact matching and detail rechecks, duplicate names on
later pages, order pagination/deduplication, no match, request budget,
broken pagination, item pagination, message-copy extension, processing/payment,
cancellation, split shipments and remaining quantities, tracking, mixed digital
items, explicit fulfillment, carrier pickup, and delivery exceptions. It also
covers readable validation/not-found messages, safe unexpected/upstream/settings
failure handling, and keeping technical error details out of responses.

Run `uv run pytest -q`. Tests mock the external GraphQL boundary; they do not
verify live Shopify permissions or replace a Cloudflare packaging check.

## Official references

- [Orders filters](https://shopify.dev/docs/api/admin-graphql/2026-07/queries/orders)
- [Order fields and access](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Order)
- [Fulfillment fields](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Fulfillment)
- [Fulfillment status keywords](https://shopify.dev/docs/api/admin-graphql/2026-07/enums/FulfillmentDisplayStatus)

- [Protected customer data and app-type access rules](https://shopify.dev/docs/apps/launch/protected-customer-data)
- [Manage and update scopes](https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes)
- [Client-credentials grant and scope updates](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant)
