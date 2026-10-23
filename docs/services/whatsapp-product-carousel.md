# Shopify product carousel preparation

## Current capability and remaining send integration

POST `/api/whatsapp/product-carousel` is separate from the working product-card
sender. It prepares multiple Shopify products for a carousel when `dry_run=true`.
It does **not** send a WhatChimp or WhatsApp message yet. With `dry_run=false`
(the default), it returns HTTP 501 `carousel_send_unconfigured` before Shopify
retrieval or any outbound send. Do not configure this as a live sending block yet.

WhatChimp publicly documents carousel templates in its
[carousel guide](https://help.whatchimp.com/docs/message-template/create-and-use-carousel-media-templates):
2 to 10 cards, up to two identically ordered buttons per card, image/video
headers, and card bodies up to 160 characters. Templates require approval.
This confirms WhatChimp's carousel feature, not a dynamic Developer API send
contract for Shopify data. Its
[template API guide](https://help.whatchimp.com/docs/whatchimp-apis/send-template-message-via-whatchimp-api)
says exact parameters depend on the template and directs users to its API Console
generator. No public carousel-specific send example was found during this work.

No guessed `/send/carousel` endpoint or guessed template component mapping is
implemented. No existing single-card credentials are transmitted to an unverified
route, no fallback batch of separate messages is sent, and no template is created.
No deployment or live message was performed for this feature.

## Requested change: finish verified WhatChimp sending

Provide the WhatChimp Developer Console carousel cURL example with all API tokens
removed. Include the approved template name, language, card count, body variable
mapping, media fields, and button types/order if templates are required.
Then map the prepared cards to the verified provider contract and reuse the
existing WhatChimp timeout, no-retry, acknowledgement and redacted diagnostic
behavior. Keep preview and sending distinguishable; acknowledge submission only
when WhatChimp explicitly accepts it. Do not claim delivery confirmation.
If the account supports only fixed carousel templates, its approved card count
and variable layout may constrain the selectable limit; validate this explicitly.
This section remains pending until the real sending integration is implemented.

## Implementation

- `app/api/product_carousel.py`: separate HTTP route, safe error boundary
- `app/schemas/product_carousel.py`: request, preview, card and button models
- `app/services/product_carousel.py`: existing collection pagination and eligibility
- `app/messaging/product_carousel_formatter.py`: name/PKR price and two button rows
- `app/main.py`: new router registration
- `tests/test_product_carousel.py`: isolated unit and endpoint tests

Reuse existing Shopify settings/client and `ProductBrowsingService` for menu
allowlists, exact tag filters, visibility, variant pricing and details retrieval.
Reuse `get_card_service` for existing WhatChimp settings and constant-time inbound
key authorization. The carousel service uses only its browsing instance; it never
calls the single-card sender. No new tokens, keys, environment variables, Shopify
GraphQL documents, or dependencies are introduced. Existing APIs are unchanged.

## Request

```http
POST /api/whatsapp/product-carousel
Content-Type: application/json
X-API-Key: YOUR_WHATCHIMP_INBOUND_API_KEY
```

```json
{
  "phone_number": "923244374905",
  "collection_id": "310360014941",
  "dry_run": true
}
```

The caller does not supply product IDs. Defaults to up to four cards. To request
up to ten, add `"limit": 10`. `limit` must be an integer from 2 to 10.
Collections accept numeric strings and full Collection GIDs. The phone must be a
digits-only string including country code, 8 to 15 digits starting with 1-9.
An optional nonempty `cursor` (max 2048 characters) resumes the previous response.
`dry_run` must be a JSON boolean. Unknown fields, including `product_id` and
`product_index`, are rejected. Phone is validated for future sending, but a dry
run neither checks its session/registration nor contacts the recipient.

All requests require the existing `WHATCHIMP_INBOUND_API_KEY`; no browsing API key
substitution occurs. Existing WhatChimp and Shopify settings must be valid under
the shared dependency even for preview. Missing key is 401, missing server
configuration is 503. `.env` values must remain private and uncommitted.

## Selection and pagination

Traverse the collection using the existing service's Shopify order, menu
membership and tags. Inspect product details in the selected collection context.
Skip products without an image or without an available selected variant. If
listing/detail selected variants change between calls, return 409 rather than
mixing a price with the wrong variant. Reject non-PKR prices; never relabel or
convert currencies. Retain the real ProductVariant GID for future ordering.
Deduplicate products within a batch, preserving first occurrence.

Fetch only as many remaining candidate products as needed to fill the requested
card count; carry the service's cursor forward so unprocessed candidates are not
silently skipped. Follow empty filtered pages. Scan at most 20 service batches,
with the existing service's own upstream page/variant limits still in effect.
Two or more eligible cards can form a short batch at the work limit; if fewer
than two were found and more pages remain, return 503 `collection_limit`.
If no more pages remain and fewer than two qualify, return 422
`insufficient_carousel_products`. Never duplicate one product to fake two cards.
Repeated/missing upstream continuation cursors return 502 `invalid_pagination`.

A carousel contains at most ten cards; it cannot contain an unlimited collection.
Collections with 2-10 eligible products can fit in one preview at `limit=10`.
Larger collections use successive cursor batches. A final remainder of one
eligible product cannot form a standalone carousel: the endpoint returns 422;
use the existing single-card endpoint for that remaining product. Pagination is
stateless, not a collection snapshot: Shopify edits can shift results, and
cross-request deduplication is not guaranteed. `count` is the returned card count,
not a fabricated full collection total. No automatic multi-message sends exist.

## Preview response

```json
{
  "status": "prepared",
  "submitted": false,
  "collection_id": "310360014941",
  "count": 2,
  "cards": [
    {
      "product_id": "gid://shopify/Product/123",
      "variant_id": "gid://shopify/ProductVariant/456",
      "title": "Example Face Wash",
      "price": "2950.00",
      "currency": "PKR",
      "media_url": "https://cdn.shopify.com/example-1.jpg",
      "body": "Example Face Wash\nPrice: PKR 2,950",
      "buttons": [
        {"id": "DETAILS:123", "title": "View Details"},
        {"id": "ADD:123", "title": "Add to Cart"}
      ]
    },
    {
      "product_id": "gid://shopify/Product/124",
      "variant_id": "gid://shopify/ProductVariant/457",
      "title": "Example Cleanser",
      "price": "1500.00",
      "currency": "PKR",
      "media_url": "https://cdn.shopify.com/example-2.jpg",
      "body": "Example Cleanser\nPrice: PKR 1,500",
      "buttons": [
        {"id": "DETAILS:124", "title": "View Details"},
        {"id": "ADD:124", "title": "Add to Cart"}
      ]
    }
  ],
  "pagination": {"has_next_page": false, "next_cursor": null}
}
```

Example IDs/images are illustrative, never hardcoded into production logic.
This is our provider-independent preview, **not** a claimed WhatChimp wire payload.
Card bodies omit product descriptions, show name and PKR price, and are bounded
to 160 characters. Full titles remain in structured data. Each card has exactly
two identically ordered reply identifiers, bounded to 256 characters with button
titles bounded to 20 characters. No cart operation or button webhook is added.
Actual template buttons must match these types/order before send mapping is enabled.
Image URLs reuse the existing safe Shopify CDN source. Preview does not download
or inspect media: JPEG/PNG format, dimensions, maximum bytes, template/card-count
compatibility and provider media acceptance still need verification for sending.

## WhatChimp flow and local inspection

For now, use Swagger `/docs` or a WhatChimp HTTP API block to inspect the preview:
POST `https://YOUR_BACKEND_DOMAIN/api/whatsapp/product-carousel`, with headers
`Content-Type: application/json`, `X-API-Key: YOUR_WHATCHIMP_INBOUND_API_KEY`, and
body:

```json
{
  "phone_number": "CURRENT_CONTACT_PHONE",
  "collection_id": "#v_selected_collection_id#",
  "limit": 4,
  "dry_run": true
}
```

Insert the real digits-only contact field using WhatChimp's field picker.
Pass back `pagination.next_cursor` with the same collection and limit to prepare
another batch when `has_next_page` is true. HTTP 200 means preview prepared;
`submitted` remains false. This block does not display a carousel in WhatsApp yet.
Do not remove `dry_run` expecting a live send: default requests return 501 until
the pending API contract is implemented. The existing `/product-card` endpoint
continues sending single interactive cards as before.

Start locally with `uv run uvicorn app.main:app --reload`; open `/docs` and supply
the existing inbound key in Authorize. Tests use mocked Shopify data and never
send messages:

```powershell
python -m pytest -q tests/test_product_carousel.py
python -m pytest -q
```

Failures return the standard `success: false`, `code`, `message` structure.
Request validation does not echo contacts. Application logs retain safe error
codes only, without credentials, exception text or tracebacks.
