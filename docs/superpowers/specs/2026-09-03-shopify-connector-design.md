# Shopify Meta Connector V1 Design

## Goal
Build a single-store FastAPI backend that runs locally in PyCharm and on Cloudflare Python Workers, securely reads Shopify data, and creates clean service boundaries for later Meta WhatsApp and LLM integrations.

## V1 boundaries
The service includes Shopify connectivity, shop metadata, products/catalog export, orders/status, legal policies, and content pages/FAQ retrieval. It does not implement Meta webhooks, LLM calls, RAG/vector storage, or customer identity verification.

## Architecture
FastAPI routes depend on `ShopifyService`. The service owns Shopify use cases and depends on `ShopifyClient`, which owns OAuth token acquisition and GraphQL transport. Configuration reads Cloudflare Worker bindings in production and `.env`/environment variables locally.

## Authentication
For a new single-store Dev Dashboard application in the same Shopify organization as the store, use the client-credentials grant. Keep Client Secret only in local ignored env files or Cloudflare encrypted secrets. Support an optional legacy pre-generated access token only as backward compatibility.

## Cloudflare
Expose the application through Cloudflare Python Workers ASGI. Use `workers.dev` for the first persistent public endpoint and move to a custom domain when the service becomes business-critical.

## Security
Do not return Shopify secrets or OAuth tokens. Order status V1 contains no customer PII. Before WhatsApp production use, add explicit customer-to-order authorization.
