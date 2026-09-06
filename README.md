# Shopify Meta Connector

A scalable FastAPI service that connects one Shopify store to a backend API. This is the Shopify/data foundation for a future Meta WhatsApp assistant.

## Current scope (V1)

- FastAPI application with versioned REST endpoints.
- Shopify GraphQL Admin API client.
- Current Shopify client-credentials authentication with automatic 24-hour token renewal.
- Shop connection test and shop metadata.
- Product catalog retrieval with cursor pagination.
- Product catalog CSV download.
- Orders and order-status lookup.
- Shopify legal policies.
- Shopify content pages and FAQ lookup.
- Cloudflare Python Workers entrypoint and configuration.
- PyCharm/local Uvicorn support.
- Automated tests.

Meta webhooks, WhatsApp routing, LLM/RAG, vector search, and customer-verification logic are intentionally outside V1.

## Architecture

```text
HTTP / future Meta webhook
        |
        v
FastAPI API layer
        |
        v
ShopifyService
        |
        v
ShopifyClient
        |
        +--> OAuth client-credentials token endpoint
        |
        +--> Shopify GraphQL Admin API
```

The API, business/service layer, and Shopify transport are deliberately separate. A future WhatsApp handler can call `ShopifyService` directly instead of duplicating Shopify logic.

## Project structure

```text
shopify-meta-connector/
├── app/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── router.py
│   │   └── v1/shopify.py
│   ├── clients/shopify_client.py
│   ├── core/
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── services/shopify_service.py
│   └── main.py
├── tests/
├── worker.py
├── wrangler.jsonc
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .dev.vars.example
└── README.md
```

## 1. Create the Shopify app

For a new integration, create the app in Shopify's **Dev Dashboard**.

1. Open the Shopify Dev Dashboard.
2. Go to **Apps** and choose **Create app**.
3. Choose **Start from Dev Dashboard**.
4. Name it, for example `Shopify Meta Connector`.
5. Create an app version.
6. For a backend-only integration, Shopify permits the default app URL if the app is not embedded.
7. Add these scopes:
   - `read_products`
   - `read_orders`
   - `read_content` (or `read_online_store_pages`)
   - `read_legal_policies`
8. Release the version.
9. Install the app on your store.
10. Open the app's **Settings** and copy the **Client ID** and **Client secret**.

New Dev Dashboard apps use the client-credentials grant for server-side integrations that act on stores in your own Shopify organization. The service exchanges the Client ID and Client Secret for a short-lived access token automatically.

> If your Shopify store and Dev Dashboard app are not in the same Shopify organization, the client-credentials grant will not work. That case needs a different OAuth/distribution flow.

## 2. Open in PyCharm

Open the extracted `shopify-meta-connector` directory as a PyCharm project.

Recommended Python: **3.13+** because Cloudflare Python Workers currently target Python 3.13 in their FastAPI setup.

Create a virtual environment in PyCharm or from PowerShell:

```powershell
cd D:\path\to\shopify-meta-connector
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_CLIENT_ID=your_client_id
SHOPIFY_CLIENT_SECRET=your_client_secret
SHOPIFY_API_VERSION=2026-07
```

Do not commit `.env`. It is already ignored by Git.

## 3. Run locally in PyCharm / terminal

From the PyCharm terminal:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

FastAPI Swagger UI lets you call every endpoint interactively.

First test:

```text
GET http://127.0.0.1:8000/api/v1/shopify/connection
```

Expected shape:

```json
{
  "connected": true,
  "shop": {
    "name": "Your Store",
    "myshopifyDomain": "your-store.myshopify.com"
  }
}
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Service information |
| GET | `/health` | Liveness check |
| GET | `/api/v1/shopify/connection` | Verify Shopify authentication/API connection |
| GET | `/api/v1/shopify/shop` | Store metadata |
| GET | `/api/v1/shopify/products` | Paginated products |
| GET | `/api/v1/shopify/products/export.csv` | Download complete product catalog as CSV |
| GET | `/api/v1/shopify/orders` | Paginated/searchable orders |
| GET | `/api/v1/shopify/orders/status?order_number=1001` | Minimal order status lookup |
| GET | `/api/v1/shopify/policies` | Store legal policies |
| GET | `/api/v1/shopify/pages` | Shopify content pages |
| GET | `/api/v1/shopify/faq` | Search pages for FAQ content |

### Pagination

Products, orders, and pages expose Shopify's cursor-based pagination. Example:

```text
GET /api/v1/shopify/products?limit=50
```

The response contains `page_info.endCursor`. Pass it back as:

```text
GET /api/v1/shopify/products?limit=50&after=<cursor>
```

The CSV catalog endpoint follows all product cursors automatically.

## Important order-status security note

`/orders/status` currently returns only non-PII order status fields and exists for backend testing. Do **not** expose order lookup directly to an unverified WhatsApp customer in the final chatbot. The future Meta flow should verify that the sender is authorized for the order before returning order details.

## 4. Run tests

```powershell
pytest -q
```

## 5. Cloudflare Workers setup

Cloudflare currently supports FastAPI directly on Python Workers through its ASGI integration. `worker.py` is the Cloudflare entrypoint while `app/main.py` remains a normal FastAPI application for local/PyCharm development.

Install `uv` if necessary:

```powershell
pip install uv
```

Install the project including Cloudflare development dependencies:

```powershell
uv sync --all-groups
```

For Cloudflare-local testing, create `.dev.vars`:

```powershell
Copy-Item .dev.vars.example .dev.vars
```

Populate it with the same Shopify values.

Run through Cloudflare locally:

```powershell
uv run pywrangler dev
```

This normally serves on `http://localhost:8787`.

## 6. Deploy permanently to Cloudflare

Sign in:

```powershell
uv run pywrangler login
```

If browser callback login is inconvenient, newer Wrangler versions also support device login:

```powershell
uv run pywrangler login --device
```

Add production secrets. Enter each value only when prompted:

```powershell
uv run pywrangler secret put SHOPIFY_STORE_DOMAIN
uv run pywrangler secret put SHOPIFY_CLIENT_ID
uv run pywrangler secret put SHOPIFY_CLIENT_SECRET
```

Deploy:

```powershell
uv run pywrangler deploy
```

With the worker name in `wrangler.jsonc`, Cloudflare will publish a persistent URL shaped like:

```text
https://shopify-meta-connector.<your-cloudflare-subdomain>.workers.dev
```

Then test:

```text
https://shopify-meta-connector.<your-cloudflare-subdomain>.workers.dev/health
https://shopify-meta-connector.<your-cloudflare-subdomain>.workers.dev/api/v1/shopify/connection
https://shopify-meta-connector.<your-cloudflare-subdomain>.workers.dev/docs
```

A `workers.dev` URL is persistent and is fine for this initial deployment. Cloudflare recommends moving business-critical production applications to a custom domain/Workers route later.

## 7. Production secrets

Never place the Shopify Client Secret in `wrangler.jsonc`, source code, GitHub, or a committed `.env` file. Cloudflare secrets are encrypted bindings. `SHOPIFY_API_VERSION` is non-sensitive and is stored as a normal Worker variable.

## Current Shopify token flow

```text
Request reaches FastAPI
      |
      v
ShopifyClient needs token
      |
      +-- cached valid token? --> use it
      |
      +-- otherwise POST /admin/oauth/access_token
              client_id
              client_secret
              grant_type=client_credentials
      |
      v
24-hour Shopify token
      |
      v
GraphQL Admin API
```

The token is cached in the Worker isolate while it remains alive and refreshed when required. No token is returned through your API endpoints.

## Next architecture phases

The intended later flow is:

```text
WhatsApp customer
      |
      v
Meta webhook
      |
      v
Message/intent router
   /            \
order intent     knowledge question
   |                 |
ShopifyService    Knowledge/RAG service
   |                 |
order status      catalog + FAQ + policies
       \             /
        LLM response layer
               |
               v
        Meta WhatsApp API
```

Recommended next phases after Shopify connectivity is verified:

1. Meta webhook module and signature verification.
2. WhatsApp message normalization.
3. Intent routing (`ORDER_STATUS`, `PRODUCT`, `FAQ_POLICY`, `GENERAL`).
4. Customer/order authorization.
5. Knowledge ingestion from products/pages/policies.
6. LLM/RAG response service.
7. Cloudflare storage/vector layer if required.
8. Observability, rate limiting, request IDs, retries, and production webhook monitoring.

## Useful commands

```powershell
# Run ordinary FastAPI locally
uvicorn app.main:app --reload

# Run tests
pytest -q

# Run using Cloudflare's local Workers runtime
uv run pywrangler dev

# Deploy
uv run pywrangler deploy
```
