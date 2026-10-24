# WhatChimp View Details button webhook

## Endpoint and WhatChimp setup

POST `/api/whatsapp/button-click?product_id=8173166231645&action=view_details`
fetches live Shopify details and submits one plain WhatsApp text reply. GET is
also supported for compatibility, but the supplied real WhatChimp capture used POST.
Paste this URL into the product's View Details button > Automation > Send data
to Webhook URL:

```text
https://shopify-meta-connector.techsupport-e35.workers.dev/api/whatsapp/button-click?product_id=8173166231645&action=view_details
```

Change product_id for each manually configured product button. Numeric Shopify
product IDs and Product GIDs are accepted and normalized; action must be exactly
`view_details`. Missing, repeated or invalid query fields return a curated 422.
No encrypted token, decryption, X-API-Key, activation switch or diagnostic mode is
used by this endpoint. Existing API-key-protected endpoints are unchanged.

This callback is intentionally unauthenticated: anyone who knows the URL can
supply a recipient and request a send. Rate limiting is abuse mitigation, not
proof that a request came from WhatChimp. Existing encryption dependencies and
internal token utilities remain installed, but the callback does not use them.
`WHATCHIMP_BUTTON_TOKEN_KEY` and previous keys are not required by this endpoint.
Existing Shopify and WhatChimp API credentials are still required for sends.

Optional URL generator (no encryption key required):

```powershell
python scripts/generate_whatchimp_button_url.py --product-id 8173166231645 --action view_details
```

## Verified callback format

The user's webhook.site test captured a POST with this JSON structure (personal
values replaced with examples):

```json
{
  "first_name": "Test Customer",
  "chat_id": "923001234567",
  "postbackid": "example-button-id",
  "user_input_data": [],
  "reply_message_id": "wamid.original-card",
  "wa_message_id": "wamid.customer-click",
  "whatsapp_bot_username": "+92 309 0000000"
}
```

`chat_id` identifies the customer recipient and is normalized as an international
digits-only number. `whatsapp_bot_username` is the business number and must never
be used as the recipient. Names and user input are not needed to send details.
`postbackid` is not treated as a Shopify product ID; product selection comes from
the URL. `wa_message_id` supplies the deduplication identifier. Neither
`reply_message_id` nor `postbackid` is a retry identifier: reusing those would risk
suppressing subsequent clicks on the same card. The capture confirms the field
names and method; stability of wa_message_id across provider retries remains to
be verified against real retry deliveries.

Existing compatible phone fields (`phone_number`, `wa_id`, `from`, contact and
subscriber phone fields) remain supported at the body root, under data/payload,
or in the query. Conflicting recipient values fail closed. No local country
code is guessed. A subscriber ID alone does not resolve a recipient.
Optional field overrides are `WHATCHIMP_BUTTON_PHONE_PATH`,
`WHATCHIMP_BUTTON_EVENT_ID_PATH` and `WHATCHIMP_BUTTON_SUBSCRIBER_PATH`.
A missing, invalid or ambiguous recipient returns 422 `customer_not_identified`
and sends nothing. Request data supports JSON and URL-encoded form bodies,
with a 64 KiB streamed limit. Invalid body: 400; unsupported content: 415;
oversized body: 413. No full payload, customer name, phone or message is logged.

## Shopify details and text reply

Reuse `ProductBrowsingService.product_details`, preserving menu/tag restrictions,
ACTIVE and Online Store visibility. Use the selected variant's own selling and
compare-at prices; show a discount only when compare-at exceeds selling price.
Send title, price/currency, valid discount, sanitized actual description and
availability. Description is capped at 2200 characters and total text at 4000.
No new image card, global incoming webhook, cart or order action is created.

Optional verified reviews use `WHATCHIMP_BUTTON_REVIEWS_VERIFIED=true` and
`WHATCHIMP_BUTTON_REVIEW_SOURCE=standard` or `judgeme_badge`. Reviews default off;
missing or failed review data never prevents the main reply. Ratings are never
invented. Existing WhatChimp text integration sends form-encoded data to
`/api/v1/whatsapp/send` with a 20-second timeout and no automatic retries. The
customer-service messaging window still applies.

A successful acknowledgement resembles:

```json
{
  "success": true,
  "action": "view_details",
  "product_id": "8173166231645",
  "customer_identified": true,
  "mode": "submitted",
  "submitted": true,
  "message": "Product details submitted to WhatChimp; delivery is not confirmed."
}
```

Provider acceptance does not confirm WhatsApp delivery. Errors contain curated
success/code/message fields, without credentials or customer contact details.

## Rate limits, retries and privacy

`WHATCHIMP_BUTTON_RATE_LIMIT` defaults to 30 requests/minute per product.
Duplicate wa_message_id/customer/product requests are suppressed for 24 hours;
without an event ID, repeated customer/product requests are suppressed for 10
seconds. A new wa_message_id permits another legitimate click. A duplicate
returns mode=duplicate and submitted=false. Claims are retained on errors to
avoid ambiguous repeated sends after upstream timeouts.

No encryption key is used for duplicate hashing. Hashes avoid storing plain
phone numbers but do not guarantee anonymity. Bounded in-memory state has 1024
rate buckets and 1024 claims. It resets on process restart/eviction and is not
shared across Worker instances, so protection is best effort. Optional D1 binding
`WHATCHIMP_BUTTON_STATE`, initialized using `scripts/button_webhook_state.sql`,
provides atomic shared state. Periodically clean up expired D1 rows.

Middleware strips query strings from application URL logs; infrastructure logs
need their own privacy configuration. No raw callback diagnostic logging exists.

## Local checks and deployment

Swagger lists required product_id and action query parameters, without a webhook
security scheme. For a real test, supply the callback JSON including chat_id.
Requests with valid recipients can send real messages; automated tests mock all
Shopify and WhatChimp clients.

```powershell
python -m pytest -q tests/test_button_webhook.py
python -m pytest -q
```

Push the change and deploy through the existing GitHub Actions workflow, then
replace the old encrypted button URL with the plaintext product/action URL.
No new GitHub secret is required for this callback. No deployment or real message
is performed during implementation. The webhook.site capture has been verified;
end-to-end delivery through the updated deployed Worker still needs a live test.
