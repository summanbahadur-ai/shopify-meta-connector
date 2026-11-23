# Selected Shopify product card via WhatChimp

## Purpose and request

POST /api/whatsapp/product-card accepts a selected product and recipient, loads
live Shopify details and submits one WhatsApp image message with a formatted
caption. Shopping, cart and checkout continue on the product's website page.
This endpoint does not send reply buttons or attach button automations.

```json
{
  "phone_number": "923244374905",
  "product_id": "8173166231645"
}
```

phone_number must contain international digits only (8-15 digits, no leading
zero). product_id accepts a positive numeric Product ID or matching Shopify GID.
The service normalizes it to a Product GID. collection_id and product_index are
not accepted. Unknown request fields return 422, preventing an old flow from
silently selecting the wrong product.

The collection and product-list APIs remain separate: select a collection, fetch
its id/title product options, save the selected product ID, then invoke this
sender with that ID and the contact phone number.

## Authentication and configuration

Send Content-Type: application/json and X-API-Key matching
WHATCHIMP_INBOUND_API_KEY. Existing constant-time authentication remains.
The server uses WHATCHIMP_API_KEY and WHATCHIMP_API_BASE_URL (default
https://api.whatchimp.com/v1), plus existing Shopify credentials.
Missing/incorrect caller key returns 401; incomplete settings return 503.
Create a new-platform API key in WhatChimp Settings > Integrations > API keys
with Send messages access to the required WhatsApp channel. Save it as GitHub
Actions secret WHATCHIMP_API_KEY alongside WHATCHIMP_INBOUND_API_KEY.
The deployment workflow uploads both to the Worker. WHATCHIMP_FROM_CHANNEL is an
optional GitHub Actions variable (a ch_ channel ID or sender number); when empty,
WhatChimp chooses the customer's last channel. Set it when the workspace has
ambiguous senders. WHATCHIMP_API_BASE_URL is an optional Actions variable; remove
an old-platform override or set it to https://api.whatchimp.com/v1.
Local .env/.dev.vars use the same names. Old tokens and phone_number_id are not
used. Updating secrets alone requires a new deployment before the live app uses them.
Keep credentials in ignored .env/.dev.vars and production Worker secrets.
The recipient must be within the applicable 24-hour customer-service window.

## Selection and pricing

ProductCardService calls ProductBrowsingService.product_details(product_id)
without scanning all products in a collection. Existing menu membership, tag
filters, ACTIVE status and Online Store publication checks remain enforced.
Missing/disallowed products return the same curated 404. Visibility does not
imply inventory availability: sold-out products can be shown with truthful
Currently unavailable wording.

The current selling price is the existing selected variant's price: first
available variant, or first variant if all are sold out. Compare-at price is
from that same variant, never an unrelated variant. A Sale tag appears only when
compare-at strictly exceeds selling price. Regular-price cards omit the Sale tag
and original price; they never display On sale: No.
Prices use Decimal, thousands separators and the actual Shopify currency.
There is no invented discount, conversion, stock quantity or delivery promise.
Website variant selection, customer discounts and prices may differ at checkout.

## Message format

Illustrative caption (values come from Shopify, not this example):

```text
*Shea Butter Lotion*

*Current price:* PKR 2,950

*Sale*

*Original price:* PKR 3,500

Available to order

*About this product*
Moisturizing body lotion.

*Shop online*
https://YOUR_STORE/products/PRODUCT_HANDLE
```

The image comes from the existing sanitized Shopify CDN image URL. The Shop
online link is the actual HTTPS Shopify product URL, not a fabricated URL or
reply-button ID. It is a clickable link in the caption, not a Shop CTA button.
HTML is removed from descriptions, script/style content omitted, title formatting
sanitized, and descriptions shortened with an ellipsis when necessary. The total
caption is capped at 1024 characters, reserving space for price, sale facts and
the complete website link. If fixed fields alone cannot fit, return 422 rather
than cutting the link. Full descriptions remain available in the details API.
If no product image is available, submit one text message with the same content.

## WhatChimp transport

The [new-platform send reference](https://dashboard.whatchimp.com/developers/endpoints/send-message)
defines JSON requests with Bearer authentication:

```text
POST https://api.whatchimp.com/v1/messages
Authorization: Bearer FROM_ENV
Content-Type: application/json
Idempotency-Key: UNIQUE_UUID

{"to":"+923244374905","text":"FORMATTED_CAPTION","media":{"url":"SHOPIFY_IMAGE_URL"}}
```

The client adds the plus prefix to validated international digits. Missing images
omit media and send the same text. Optional WHATCHIMP_FROM_CHANNEL becomes from.
Both card and button-details clients share this transport. No old form fields,
reply buttons or media uploads are sent.

Use httpx.AsyncClient, 20-second timeout, no redirects and no automatic retries.
Each send gets a fresh Idempotency-Key; it is not persisted across separate HTTP
requests, so a manual retry is a new send. Success requires HTTP 2xx, status
accepted and a msg_ ID; acceptance does not confirm delivery. Invalid JSON or
acknowledgements and unknown provider errors return curated 502 errors.
Authentication maps to whatchimp_authentication (502), rate limiting to
whatchimp_rate_limit (429), and timeout/connection failures to 504/502.
Known error codes window_closed, no_conversation, contact_blocked and
channel_not_connected map to curated whatchimp_-prefixed 409 errors; from_required
maps to whatchimp_from_required (422). Raw provider messages are never exposed.
Timeout/connection failures have unknown send status: check WhatChimp before
retrying to avoid duplicates. Diagnostics retain only redacted structure and HTTP
status; credentials, contact data and raw upstream messages are not logged or returned.

## Response

```json
{
  "success": true,
  "message": "Product card submitted to WhatChimp",
  "phone_number": "923244374905",
  "product": {
    "id": "gid://shopify/Product/8173166231645",
    "variant_id": "gid://shopify/ProductVariant/REAL_VARIANT_ID",
    "title": "Example product",
    "price": "1650.00",
    "currency": "PKR",
    "on_sale": false,
    "product_url": "https://YOUR_STORE/products/PRODUCT_HANDLE"
  }
}
```

Acceptance is not delivery confirmation. There is no collection/index metadata.
Errors return success=false, stable code and curated message. Common statuses:
401 authorization, 404 unavailable product, 422 input/caption limit, 429 provider
rate limit, 502 Shopify/provider failure, 503 configuration/lookup work limit,
504 provider timeout.

## WhatChimp flow, Swagger and tests

Configure the existing HTTP API block:

```text
Method: POST
URL: https://YOUR_BACKEND_DOMAIN/api/whatsapp/product-card
Content-Type: application/json
X-API-Key: YOUR_WHATCHIMP_INBOUND_API_KEY
```

```json
{
  "phone_number": "CURRENT_CONTACT_PHONE",
  "product_id": "#v_selected_product_id#"
}
```

Use WhatChimp's field picker for the real current-contact phone variable and
your selected-product variable. Do not send the selected collection ID here.
After deploying, /docs shows the new request model. Authorize the inbound key
and execute with a test recipient and selected product ID. A real execution sends
a real message; automated tests mock every external send.

```powershell
python -m pytest -q tests/test_product_card.py
python -m pytest -q
```

Source files: app/api/product_card.py, app/schemas/product_card.py,
app/services/product_card.py, app/messaging/product_card_messages.py,
app/messaging/product_card_formatter.py and app/clients/whatchimp_client.py.
Live validation through the local service received HTTP 201 from the new API,
and the test recipient confirmed receipt of the product card after the dashboard
switch. Deployment and validation through the production Worker remain separate
checks. Automated tests continue to mock external sends.
