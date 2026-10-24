# Encrypted WhatChimp View Details button webhook

## Behavior

GET or POST `/api/whatsapp/button-click?token=ENCRYPTED_TOKEN` validates and decrypts
the product-specific token, extracts the customer phone from the callback, fetches
live Shopify product details, and submits a plain WhatsApp text message.
There is no diagnostic mode, enable/disable switch or payload-verification gate.
The only new required credential is `WHATCHIMP_BUTTON_TOKEN_KEY`; existing Shopify
and WhatChimp API credentials are reused. Missing/tampered tokens return 401.
Existing X-API-Key endpoints keep their existing authentication unchanged.
No global incoming-message receiver, new image card, cart or order flow is added.

## Key and product URL

The dedicated Fernet key is already present in the ignored local `.env` if it was
previously generated. Keep the same key in the deployed Worker secret:

```dotenv
WHATCHIMP_BUTTON_TOKEN_KEY=your_generated_fernet_key
```

If creating a new key, generate it securely and store it without committing it:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate one product-specific URL:

```powershell
python scripts/generate_whatchimp_button_url.py --product-id 8173166231645 --action view_details
```

Paste the output into WhatChimp's View Details button -> Automation -> Send data
to Webhook URL. The generated URL contains an encrypted token, not a plaintext
product ID. No X-API-Key header is required for this callback. The URL is a bearer
credential: do not expose it in public logs/issues. Tokens identify a product and
view_details action, not customer identity or ownership.

Tokens do not expire after a few minutes. Optional comma-separated
`WHATCHIMP_BUTTON_TOKEN_PREVIOUS_KEYS` permits key rotation; new tokens use the
current key and old tokens remain accepted while their key is retained. Removing
an old key revokes all its URLs. Individual token revocation is not implemented.
Never reuse Shopify or WhatChimp API credentials as the encryption key.

## Recipient data

The callback must supply one unambiguous valid international customer number.
Accepted relative fields are `phone_number`, `wa_id`, `from`, `contact.phone`,
`contact.wa_id`, `subscriber.phone_number` and `subscriber.wa_id`. These can appear
at the body root, under body `data`/`payload`, or in query parameters. Numeric
strings with country code and optional plus sign are normalized using the existing
phone validator. No country code is guessed for local numbers. The merchant's
`phone_number_id` is never a recipient fallback. Conflicting phone values fail
closed. A subscriber ID alone is not resolved through an invented provider API.

Example accepted POST body (illustrative, not a verified WhatChimp capture):

```json
{"phone_number":"923244374905","event_id":"unique-button-click-id"}
```

An empty callback or missing/invalid/ambiguous number returns HTTP 422
`customer_not_identified`; no message is sent. The actual WhatChimp button callback
format is still unverified. If its fields differ, optional overrides
`WHATCHIMP_BUTTON_PHONE_PATH`, `WHATCHIMP_BUTTON_EVENT_ID_PATH` and
`WHATCHIMP_BUTTON_SUBSCRIBER_PATH` accept dot paths such as `body.contact.phone`
or `query.phone_number`. These are field overrides, not enable switches.

The endpoint supports empty/JSON/form-encoded requests, with a 64 KiB streamed
body limit. Authentication runs before Shopify lookup or outbound send. Invalid
bodies return 400, unsupported content 415, oversized requests 413.

## Live details and response

Reuse `ProductBrowsingService.product_details` for current products, including
menu/tag access, ACTIVE/Online Store visibility and same-variant selling/compare-at
prices. Token contents never bypass product visibility. Send title, current price,
valid discount percentage/original price, sanitized description and availability.
Description is limited to 2200 characters, total text to 4000. No image-card sender
is called. The text endpoint is `/api/v1/whatsapp/send`, with existing credentials,
form encoding, a 20-second timeout, no automatic retries and explicit status-1
acknowledgement. Acceptance is not delivery; the customer-service window still
applies.

A submitted response contains `success: true`, `mode: submitted`, `submitted: true`,
the action/product ID and customer_identified boolean. A suppressed retry returns
`mode: duplicate`, `submitted: false`. Errors use success/code/message and contain
no tokens or contact data.

## Optional reviews

A read-only sample-product check found Judge.me `judgeme.badge` and
`judgeme.widget` metafields. Review data remains optional: enable only a verified
source with `WHATCHIMP_BUTTON_REVIEWS_VERIFIED=true`, choosing
`WHATCHIMP_BUTTON_REVIEW_SOURCE=judgeme_badge` or `standard`. Default lookup is off;
missing or failing reviews never block current product details.

The Judge.me source uses one unambiguous badge's documented average-rating/count
attributes. Standard source uses configured Shopify rating/count metafields.
No invented ratings, reviewer excerpts or claims are shown. Source references:
[Judge.me metafields](https://judge.me/help/en/articles/8394936-displaying-product-ratings-and-review-counts-with-judge-me-metafields).

## Retry protection, rate limits and privacy

Rate limiting defaults to 30 valid requests/minute per product. Duplicate events
are suppressed for 24 hours when an event ID is present; otherwise phone/product
clicks are suppressed for 10 seconds. Claims are retained after failures/timeouts
to avoid ambiguous repeat sends. Sender transport performs no automatic retry.

Without a database, bounded in-process state (1024 rate buckets and 1024 claims)
provides best-effort protection. It resets on restart/eviction and is not shared
across Worker isolates; duplicate sends across instances are possible. Optional
D1 binding `WHATCHIMP_BUTTON_STATE` with `scripts/button_webhook_state.sql` provides
atomic durable state. No D1 database is required to run this endpoint. With D1,
periodically remove expired rows. Key rotation can reset duplicate hashes.

Middleware removes webhook query strings from application/server URL logging;
common Python request logs redact token values. No payload-shape diagnostic
logging is performed. Infrastructure/proxy logs need their own query redaction,
since Cloudflare sees the original URL before FastAPI. A valid token is reusable:
keep it private, protect the endpoint against abuse and never log full URLs.

## Running and testing

Existing `.env` Shopify/WhatChimp credentials plus the dedicated Fernet key are
sufficient locally; no webhook activation flags are required. Restart Uvicorn:

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m pytest -q tests/test_button_webhook.py
python -m pytest -q
```

Swagger shows GET/POST and the EncryptedButtonToken query security scheme.
A request containing a real token and recipient now sends a real text message;
unit tests mock all external clients. Existing product-card tests remain unchanged.
No deployment or real customer messages are performed during this code change.

Worker packaging is still unverified locally: the earlier Windows Pyodide
interpreter failed with `ModuleNotFoundError: No module named python` before
bundling. The supported dependency range allows Worker cryptography 45.0.5 and
local 49.0.0. Verify the existing Linux CI sync/preflight/dry-run before deployment.
