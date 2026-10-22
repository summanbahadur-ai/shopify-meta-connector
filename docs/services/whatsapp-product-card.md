# WhatChimp interactive Shopify product cards

## Purpose and implementation

POST `/api/whatsapp/product-card` submits one image/text-header interactive reply
button message through WhatChimp. Acceptance is not delivery confirmation.
Existing Shopify routes, product browsing, order lookup, and integrations retain
their behavior. No cart persistence, order creation, checkout, payments, addresses,
or reply webhooks are implemented.

- HTTP/authentication and safe errors: `app/api/product_card.py`
- Request and response models: `app/schemas/product_card.py`
- On-demand Worker/local settings: `WhatChimpSettings` in `app/core/config.py`
- Product selection and send orchestration: `app/services/product_card.py`
- Existing Shopify integration: `ProductBrowsingService` and `ShopifyClient`
- Text, buttons, and formatting: `app/messaging/product_card_messages.py` and
  `app/messaging/product_card_formatter.py` (`build_product_card`)
- Outbound transport: `app/clients/whatchimp_client.py`
- Tests: `tests/test_product_card.py`

## Settings and security

Set the following only in local `.env` (or `.dev.vars` for local Workers) and in
production Worker secrets. Both real local files are already gitignored.

| Variable | Purpose |
| --- | --- |
| `WHATCHIMP_API_TOKEN` | Private WhatChimp Developer API token |
| `WHATCHIMP_PHONE_NUMBER_ID` | Digits-only sending account phone number ID |
| `WHATCHIMP_API_BASE_URL` | Default `https://app.whatchimp.com/api/v1`; HTTPS required |
| `WHATCHIMP_INBOUND_API_KEY` | Long random key, independent of product browsing key |

The GitHub workflow optionally uploads the three WhatChimp repository secrets
when supplied together. It uses the optional repository variable
`WHATCHIMP_API_BASE_URL` or the default URL. With none supplied, existing Shopify
deployments still work and this endpoint fails closed until configured. Removing
GitHub secrets does not remove old Worker secrets; explicitly remove those when
disabling the integration. No WhatChimp settings are required for existing routes.

Send `X-API-Key` matching `WHATCHIMP_INBOUND_API_KEY`; comparison is constant time.
Missing/wrong caller key returns 401, missing server configuration returns 503.
Only this new sender uses this key. Shopify and WhatChimp API tokens stay on the
backend. No credentials go to WhatsApp, API responses, or application logs.
Settings are validated on use; secret configuration objects have no value repr.
The recipient must have an active 24-hour customer-service session. The caller is
responsible for session eligibility and appropriate recipient selection. This
endpoint does not check ownership or query WhatChimp conversation windows.

## Input and output

```http
POST /api/whatsapp/product-card
Content-Type: application/json
X-API-Key: YOUR_CONFIGURED_INBOUND_API_KEY
```

```json
{
  "phone_number": "923001234567",
  "collection_id": "310360113245",
  "product_index": 0
}
```

Phone is a digits-only string, 8?15 digits, starts with 1?9, country code included
(no plus sign or spaces). This checks syntax, not WhatsApp registration or actual
number ownership. Collection accepts a numeric ID string or Collection GID.
`product_index` defaults to 0 and must be a non-negative JSON integer.

Example acceptance response (illustrative product):

```json
{
  "success": true,
  "message": "Product card submitted to WhatChimp",
  "phone_number": "923001234567",
  "collection_id": "310360113245",
  "product_index": 0,
  "product": {
    "id": "gid://shopify/Product/15456526106717",
    "variant_id": "gid://shopify/ProductVariant/123456789",
    "title": "Shea Butter Lotion",
    "price": "2950.00",
    "currency": "PKR"
  }
}
```

Collection ID in the response is numeric; product and selected variant retain
real Shopify GIDs. No message is considered delivered merely because accepted.

## Selection and work limits

Reuse `collection_products(limit=50, cursor=...)` and follow pagination, including
empty filtered pages, up to 20 service pages. Count every returned visible,
menu-authorized, tag-matching product in Shopify default order before selecting
the zero-based index. This produces an actual total, never an assumed five.
Each existing service page retains its own upstream page/variant scan limits.
If more data remains after the cap, fail with 503 before sending. Repeated or
missing continuation cursors fail with 502. No collection snapshot or cross-request
cache is stored: Shopify edits between requests can change positions/counts.
Large collections can exceed execution/time budgets; a future snapshot/index
mechanism may be needed. The total is the visible menu-filtered product count,
including sold-out products, not an inventory count.

Fetch the selected product's details through the same service and collection
context. Require its selected pricing variant to remain unchanged and available;
sold-out/missing selected variants return 409 before sending. Missing/invalid
prices or malformed upstream products fail safely without guessed data. Only PKR
prices are supported; other currencies return 422 without conversion/relabeling.

## Message and navigation

Use Shopify title (bounded to 200 characters), PKR price with thousands separators,
and `Product 1 of N`. The initial card omits the description. The existing product
details service retains the full sanitized description for the View Details flow;
automatic button-reply handling remains pending. Use a safe Shopify CDN image URL when
available; otherwise omit `media_url` and supply a text header (at most 60 chars).

The three reply buttons have titles no longer than 20 characters and IDs bounded
to 256 characters:

| Button | ID example | Future interpretation |
| --- | --- | --- |
| View Details | `DETAILS:15456526106717` | Product numeric ID |
| Add to Cart | `ADD:15456526106717` | Product numeric ID; resolve real variant later |
| Next Product | `NEXT:310360113245:1` | Collection numeric ID and next zero-based index |
| Back to Categories (last product, replaces Next) | `CATEGORIES:1` | First categories page |

There are exactly three buttons, never four. All are reply identifiers, not URL
buttons or implemented actions. No click currently changes a cart or sends the
next card automatically. A future reply webhook/flow router must interpret IDs,
verify collection access again, and invoke this endpoint for Next. Do not deploy
button handling that promises a successful cart operation before it exists.

## WhatChimp transport and diagnostics

POST `{WHATCHIMP_API_BASE_URL}/whatsapp/send/interactive-buttons` using
`httpx.AsyncClient`, 20-second timeout, no redirects and no automatic retry.
Send `application/x-www-form-urlencoded` fields `apiToken`, `phone_number_id`,
`phone_number`, `message`, `buttons` (JSON-encoded array), `button_footer_text`,
and either optional `media_url` or `button_header_text`.

Official reference checked during implementation:
[WhatChimp Developer API](https://help.whatchimp.com/docs/whatchimp-apis/getting-started-with-whatchimp-api)
documents POST form fields and JSON response `status: "1"` (success), `"0"`
(failure). This client requires HTTP 2xx and status string/integer 1; an HTTP 200
alone or `success: true` without this acknowledgement is not enough.

**Unverified endpoint-specific behavior:** the accessible official public guide
does not list `/whatsapp/send/interactive-buttons`. Its path/field names come from
the requested specification. JSON-array encoding within the form field, CDN image
headers, text-header fallback, and dynamic reply ID handling must be verified
against the account's Developer Console before production use. No live message
was sent during implementation. General API encoding/acknowledgement is verified
against the official guide; endpoint compatibility is not claimed as verified.

The client retains `last_diagnostics` in memory: HTTP status plus the parsed
upstream JSON structure, with all values and unknown keys redacted (including
contacts, tokens, message IDs/text). Non-JSON response bodies are not retained.
No raw upstream response is returned or logged. Diagnostics live for the client
instance only, not persistent storage; inspect through an internal debugger/test
or add an explicitly approved secure diagnostic sink later.

## Errors

Failures return `{"success": false, "code": "...", "message": "..."}`.
Validation never echoes recipient input or exception text. Logs contain only
curated error codes, without exception text or tracebacks.

| HTTP | Typical code/meaning |
| --- | --- |
| 401 | `unauthorized` |
| 404 | `empty_collection`, `product_index_out_of_range`, or menu access `not_found` |
| 409 | `variant_unavailable`, `product_changed` |
| 422 | `invalid_request`, `unsupported_currency` |
| 429 | `whatchimp_rate_limit` |
| 502 | `shopify_unavailable`, `whatchimp_authentication`, `whatchimp_rejected`, `whatchimp_connection`, invalid upstream data |
| 503 | `configuration_error`, `collection_limit`, existing Shopify lookup budget |
| 504 | `whatchimp_timeout` |

A timeout/connection error may occur after a send was accepted. Check message
status in WhatChimp before manually retrying. Repeating this POST can send another
message; no idempotency guarantee is implemented. Application logging avoids
secrets, but operators must also avoid request-body/token logging in proxies.

## WhatChimp HTTP API block

Method: **POST**. URL: `https://YOUR_BACKEND_DOMAIN/api/whatsapp/product-card`.
Headers: `Content-Type: application/json` and
`X-API-Key: YOUR_CONFIGURED_INBOUND_API_KEY`.

```json
{
  "phone_number": "CURRENT_CONTACT_PHONE",
  "collection_id": "#v_selected_collection_id#",
  "product_index": 0
}
```

`CURRENT_CONTACT_PHONE` is a placeholder: insert the real contact phone variable
using WhatChimp's field picker, ensuring it produces digits with country code.
The selected collection must be a real collection ID, not a `PAGE:2` menu row.
Handle errors in the flow without claiming a message was sent. WhatChimp flow
configuration and future button-reply routing are separate from this endpoint.

## Local running and tests

Run `uv sync --all-groups`, configure local `.env`, then
`uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
Open `http://127.0.0.1:8000/docs`, authorize the product-card operation's API-key
scheme with the inbound key, expand POST `/api/whatsapp/product-card`, and fill
its example JSON body. **Executing with real settings sends a real message.**
Use only a deliberate test recipient with an active session when ready; tests
below never send live messages and do not need real credentials.

```powershell
python -m pytest -q tests/test_product_card.py
python -m pytest -q
```

Tests cover mocked Shopify HTTP and WhatChimp form requests, success and failures,
ID forms, auth/configuration, validation, pagination/limits, image fallback,
formatting/navigation, unavailable variants, safe logs/errors, and no send retries.
