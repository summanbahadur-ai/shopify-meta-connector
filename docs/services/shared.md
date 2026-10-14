# Shared Shopify API behavior

## Implementation

- Settings: `app/core/config.py`
- Client: `app/clients/shopify_client.py`
- Dependency construction: `app/api/dependencies.py`
- Error handling: `app/main.py`, `app/core/exceptions.py`
- Route prefixes: `app/api/router.py`, `app/api/v1/shopify.py`
- Existing settings tests: `tests/test_settings.py`

## Configuration input

| Setting | Meaning |
| --- | --- |
| `SHOPIFY_STORE_DOMAIN` | Required Shopify domain, e.g. `demo.myshopify.com` |
| `SHOPIFY_CLIENT_ID` | Required unless a legacy access token is supplied |
| `SHOPIFY_CLIENT_SECRET` | Required unless a legacy access token is supplied |
| `SHOPIFY_API_VERSION` | Defaults to `2026-07` |
| `SHOPIFY_ACCESS_TOKEN` | Optional legacy token; bypasses token exchange |

Local Python loads `.env` without overriding existing process variables.
Worker requests first use `request.scope["env"]`; if that configuration is
invalid, settings fall back to process environment variables. Domain settings
have surrounding whitespace, an HTTP(S) prefix, and trailing slashes removed.

## External calls and responses

1. Unless a legacy or cached token is available, POST
   `https://{store}/admin/oauth/access_token` with form fields
   `grant_type=client_credentials`, `client_id`, and `client_secret`.
2. Expect JSON with `access_token` and optional `expires_in` (default `86399`
   seconds). Cache the token in process memory by store domain. Reuse it only
   when its expiry is more than 60 seconds away. Cache is not durable storage.
3. POST `https://{store}/admin/api/{version}/graphql.json` with JSON
   `{"query": "<GraphQL document>", "variables": {}}` and headers
   `Content-Type: application/json`, `X-Shopify-Access-Token: <private token>`.
4. Shopify normally returns `{"data": {...}}`; the client returns only the
   inner `data` dictionary (or `{}` if it is absent). Service methods then
   select or reshape that data as described in the other contracts.

The HTTP timeout is 20 seconds by default per client request. There is no
automatic retry. A GraphQL HTTP 401/403 clears the cached token and fails the
current request; it does not retry that request with a fresh token.

## Public error behavior

| Condition | Public HTTP response |
| --- | --- |
| Missing required settings | 500, `{"detail": "<configuration message>"}` |
| Token request network error, HTTP error, or missing access_token | 502, `{"detail": "<authentication message>"}` |
| GraphQL HTTP 401/403 | 502, `{"detail": "Shopify rejected the token or configured app scopes"}` |
| GraphQL network error, other HTTP error, or nonempty errors array | 502, `{"detail": "<Shopify API message>"}` |
| Invalid HTTP query parameters | 422 with FastAPI validation details |

GraphQL errors cause failure even if a partial `data` payload exists. Malformed
JSON and unexpected/missing response fields do not have dedicated error handling;
do not assume all upstream failures become the structured 502 responses above.

There is currently no caller authentication dependency on these Shopify routes.
Do not assume order data is protected by customer authorization.

## Requested change

None pending.
