# Shopify Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a PyCharm-ready FastAPI Shopify connector deployable on Cloudflare Python Workers.

**Architecture:** Versioned API routes call a Shopify service, which calls an async GraphQL client. Authentication uses Shopify's client-credentials grant and Cloudflare secrets in production.

**Tech Stack:** Python 3.13+, FastAPI, httpx, pytest, Cloudflare Python Workers, pywrangler, Shopify GraphQL Admin API.

**Spec:** `docs/superpowers/specs/2026-09-03-shopify-connector-design.md`

## Global Constraints
- Single Shopify store only.
- Cloudflare Python Workers deployment.
- Shopify access is read-only in V1.
- No Meta/WhatsApp or LLM implementation in V1.
- Secrets must never be committed.

---

### Task 1: Application foundation
**Files:** `app/main.py`, `app/api/router.py`, tests.
- [x] Define health/root tests and observe them fail before implementation.
- [x] Implement FastAPI app and versioned router.
- [x] Verify tests pass.

### Task 2: Shopify configuration and transport
**Files:** `app/core/config.py`, `app/core/exceptions.py`, `app/clients/shopify_client.py`, tests.
- [x] Test required Shopify settings and URLs.
- [x] Implement Worker/local configuration boundary.
- [x] Implement client-credentials token acquisition/cache and async GraphQL transport.
- [x] Map auth, HTTP, and GraphQL failures to typed exceptions.

### Task 3: Shopify data service and endpoints
**Files:** `app/services/shopify_service.py`, `app/api/v1/shopify.py`, tests.
- [x] Test connection, product, order, policy, and page service behavior.
- [x] Implement shop connection and metadata.
- [x] Implement product cursor pagination and full CSV catalog export.
- [x] Implement minimal order-status lookup without PII.
- [x] Implement policies and FAQ/page retrieval.

### Task 4: Cloudflare and developer workflow
**Files:** `worker.py`, `wrangler.jsonc`, `pyproject.toml`, `.env.example`, `.dev.vars.example`, `README.md`.
- [x] Add ASGI Worker entrypoint.
- [x] Declare Python Workers compatibility and secrets.
- [x] Document PyCharm/local run, Shopify setup, tests, Cloudflare login/secrets/deploy, and persistent workers.dev URL.
- [x] Run full tests and compile verification before packaging.
