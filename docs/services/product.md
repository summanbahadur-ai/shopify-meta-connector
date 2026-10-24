# Menu-based product browsing

## Purpose and architecture

Customers select a collection and then a product. Lists contain only numeric
Shopify IDs and titles, suitable for mapping into WhatChimp fields. API routes
are in app/api/product_browsing.py, business rules in
app/services/product_browsing.py, GraphQL in app/clients/product_queries.py,
and models in app/schemas/product_browsing.py. Existing Shopify clients,
authentication and error handling are reused. Order APIs are unchanged.

## Authentication and Shopify setup

All browsing endpoints require X-API-Key matching PRODUCT_BROWSING_API_KEY.
Missing/wrong caller key returns 401; missing server configuration returns 503.
Never expose Shopify credentials. Use existing SHOPIFY_STORE_DOMAIN,
SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET and SHOPIFY_API_VERSION settings.
The configured menu is gid://shopify/Menu/235088314461. Shopify permissions
read_products and read_online_store_navigation are required; changing scopes
requires releasing the app configuration and approving the installation.

## Endpoints and responses

All paths have prefix /api/v1/shopify. Numeric IDs and matching Shopify GIDs
are accepted as inputs. List responses use numeric strings; detail responses
retain full Shopify GIDs and actual variant IDs.

GET /products/collections returns all unique valid menu collections in menu order.
There is no page parameter, More row or pagination metadata. It returns only:

```json
{
  "collections": [
    {"id": "310362112093", "title": "New & Featured"},
    {"id": "310360014941", "title": "Facewash & Cleansers"}
  ]
}
```

No menu_id, menu_title, total, URL or tags are exposed. The internal menu retains
tags and URLs for access rules; removing response fields does not broaden access.
An empty configured menu returns {"collections": []}; a missing menu returns 502.

GET /products/collections/{collection_id}/products and its query alias
GET /products/collection-products?collection_id=310360014941 return:

```json
{
  "products": [
    {"id": "8173166231645", "title": "Face Wash Rice & Niacinamide"}
  ]
}
```

These routes return only products with id/title. No collection metadata,
prices, descriptions, images, variants or pagination fields are included.
They load the full visible collection by following Shopify cursors internally;
limit and cursor are no longer public inputs. Empty collections return
{"products": []}. Large selections that exceed the work budget fail with 503
lookup_limit rather than returning a silently truncated list. The existing
rich internal collection_products method remains paginated for product-card
and carousel services, preserving their pricing/image/variant data.

GET /products/{product_id}?collection_id=... and
GET /products/details?product_id=...&collection_id=... return existing full product
details, actual selected variant ID and deterministic WhatsApp message unchanged.
Use the query aliases for slash-containing GIDs. IDs must be positive numeric
strings or matching resource GIDs; invalid IDs return 422. Query IDs are bounded
to 100 characters. Credentials and raw upstream error details are never returned.

## Menu authorization and product visibility

Traverse all three supported menu levels depth first. Include COLLECTION links
with valid Collection resource IDs, deduplicating by GID and preserving the first
link's label, tags, URL and position internally. Never list all store collections.
Products must belong to an allowed menu collection, have ACTIVE status, and have
an absolute HTTPS onlineStoreUrl. Menu tags use case-insensitive exact AND
matching. A later duplicate without tags does not broaden the first link.
Disallowed/missing collections and products return curated 404 not_found.
Product details with collection context must match that collection and its tags;
without context, require a matching allowed collection membership. No unrestricted
GET /products root listing is exposed.

## Internal data and work limits

List options reuse the existing product retrieval service, preserving Shopify
order and scanning filtered pages even when a page contains no visible products.
The options aggregator follows up to 20 service pages, requesting limit=50;
each service page scans up to 10 Shopify pages of up to 10 products. Missing or
repeated continuation cursors fail with 502. All results are buffered before
returning, so very large collections may exceed Worker execution budgets.
Collections have no artificial display cap. These endpoints do not enforce
WhatsApp's 10-row interactive-list limit; the caller must choose its display UI.

Rich internal summaries and details keep full sanitized descriptions, one
selling price/currency from the first available variant (first variant if all
sold out), its real variant GID, and that same variant's compare-at price.
Discounts exist only when compare-at exceeds selling price. Money uses Decimal.
Details include variants, vendor, type, availability and formatted WhatsApp text.
Prices are shop-currency defaults, not customer-specific/cart discounts. Image
URLs are HTTPS Shopify CDN URLs or null. Variant and membership scans each have
a 20-page budget; exceeding it fails closed. Existing bounded Shopify retries,
timeouts, product messaging and product-card behavior remain unchanged.

## WhatChimp setup and local testing

Configure the HTTP block to GET /api/v1/shopify/products/collections with
X-API-Key. Map the collections array using id/title. Save the chosen collection
ID, then call /api/v1/shopify/products/collection-products?collection_id=SELECTED_ID
with the same header. Map products using id/title; use the selected product ID
for the details API or the separate View Details webhook integration.
Remove former total/menu/tag/URL and pagination mappings from the flow.

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m pytest -q tests/test_product_browsing.py
python -m pytest -q
```

Use /docs to authorize X-API-Key and try both list routes. Tests mock Shopify.
No deployment or real WhatsApp message is performed during this change.

## Exact GraphQL documents

The following are the fully expanded documents sent by the implementation.
Variables are parameterized; document fragments are fixed application constants.

### MENU_QUERY

```graphql
query GetNavigationMenu($menuId: ID!) {
  menu(id: $menuId) {
    id title handle
    items {
      id title type resourceId url tags
      items {
        id title type resourceId url tags
        items { id title type resourceId url tags }
      }
    }
  }
}
```

### COLLECTION_PRODUCTS_QUERY

```graphql
query GetCollectionProducts($collectionId: ID!, $first: Int!, $after: String) {
  collection(id: $collectionId) {
    id title
    products(first: $first, after: $after) {
      edges { cursor node {

  id title handle status tags onlineStoreUrl description descriptionHtml
  featuredMedia { ... on MediaImage { image { url altText } } }
  priceRangeV2 {
    minVariantPrice { amount currencyCode }
    maxVariantPrice { amount currencyCode }
  }

        variants(first: 50) {
          nodes { id price compareAtPrice availableForSale }
          pageInfo { hasNextPage endCursor }
        }
      } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

### PRODUCT_DETAILS_QUERY

```graphql
query GetProductDetails($productId: ID!) {
  product(id: $productId) {

  id title handle status tags onlineStoreUrl description descriptionHtml
  featuredMedia { ... on MediaImage { image { url altText } } }
  priceRangeV2 {
    minVariantPrice { amount currencyCode }
    maxVariantPrice { amount currencyCode }
  }

    vendor productType
    variants(first: 50) {
      nodes { 
  id title price compareAtPrice availableForSale
  selectedOptions { name value }
 }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

### VARIANTS_QUERY

```graphql
query GetProductVariants($productId: ID!, $after: String!) {
  product(id: $productId) {
    variants(first: 50, after: $after) {
      nodes { 
  id title price compareAtPrice availableForSale
  selectedOptions { name value }
 }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

### MEMBERSHIP_QUERY

```graphql
query ProductInCollection($productId: ID!, $collectionId: ID!) {
  product(id: $productId) { inCollection(id: $collectionId) }
}
```

### PRODUCT_COLLECTIONS_QUERY

```graphql
query ProductMenuMembership($productId: ID!, $after: String) {
  product(id: $productId) {
    collections(first: 50, after: $after) {
      nodes { id }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

## Interactive WhatChimp product cards

POST `/api/whatsapp/product-card` reuses this browsing service to submit one
interactive product card, protected by a separate inbound key. See
[whatsapp-product-card.md](whatsapp-product-card.md) for its complete contract,
settings, examples, WhatChimp HTTP block setup, limits, and unverified API details.
Existing browsing responses and access rules remain unchanged.

## Multi-product carousel preview

POST `/api/whatsapp/product-carousel` reuses this service for up to 10 products
(default 4) with images and available variants. The separate endpoint currently
requires `dry_run=true` and does not send. See
[whatsapp-product-carousel.md](whatsapp-product-carousel.md) for selection,
pagination, examples and the pending WhatChimp carousel send contract.

## Manual View Details buttons

GET/POST `/api/whatsapp/button-click?product_id=8173166231645&action=view_details`
fetches live Shopify details and sends plain text to WhatChimp's customer `chat_id`.
This public callback uses no token decryption or X-API-Key. Existing protected
endpoints retain their authentication. WhatChimp's captured request is POST JSON.
See [whatsapp-button-details.md](whatsapp-button-details.md) for the captured payload,
setup, duplicate suppression and security limitations.
