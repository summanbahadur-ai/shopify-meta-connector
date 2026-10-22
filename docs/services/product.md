# Menu-based product browsing

## Purpose and customer journey

Dr Elements' WhatsApp customer selects Product Information, chooses a collection
from the configured Shopify navigation menu, then chooses a product. The backend
returns structured facts and a deterministic WhatsApp message without an LLM.
WhatChimp flows are configured separately; this feature does not change them.

Customer browsing uses only menu-scoped collections and products.
Order tracking remains unchanged.

## Architecture

`app/api/product_browsing.py` handles HTTP, API-key authentication, dependencies,
and curated error responses. `app/services/product_browsing.py` enforces menu
membership, visibility, pagination, tags, and mapping. It reuses the existing
`ShopifyClient` and its OAuth/token cache through `get_shopify_service`.
`app/clients/product_queries.py` holds parameterized GraphQL documents and the
menu constant. Pydantic models are in `app/schemas/product_browsing.py`.
`app/messaging/product_messages.py` holds extensible wording/limits;
`product_formatter.py` sanitizes descriptions and formats customer text.

## Shopify settings and app permissions

Store: Doctors Elements, canonical Shopify domain `e6c1db-db.myshopify.com`,
public website `https://drelements.com`. Set `SHOPIFY_STORE_DOMAIN` accordingly.
The existing stable API default remains `2026-07`; use no unstable/RC versions.
Menu constant `PRODUCT_MENU_ID`: `gid://shopify/Menu/235088314461`.
It is not a request input. Menu source:
https://admin.shopify.com/store/doctorselements/content/menus/235088314461

Required scopes: `read_online_store_navigation` and `read_products`, in addition
to existing order scopes. In Shopify Dev Dashboard open the existing app,
edit its configuration/version, add these two scopes without removing existing
ones, and release the new version. Update/reauthorize the store installation to
approve the changed access. Obtain a fresh access token after approval (restart
the backend to clear its cached client-credentials token; replace a legacy static
token if using one). Missing permission returns a curated 502, never an empty
successful result. If 502 persists, check scopes, installation, menu, and credentials.

Official schema references:
[Menu](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Menu),
[MenuItem](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/MenuItem),
[Product](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/Product),
[ProductVariant](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/ProductVariant).
Product's reference includes `compareAtPriceRange`; this implementation uses
variant `price`/`compareAtPrice` pairs instead, avoiding comparisons of unrelated
range endpoints. No deprecated pricing/publication fields are used.

## Security and setup

Set a long random `PRODUCT_BROWSING_API_KEY` in `.env` for local use.
Send it in the `X-API-Key` header for every browsing request. Do not put it in
URLs or customer-visible WhatsApp messages. Compare keys in constant time.
Missing server configuration returns 503; missing/wrong client key returns 401.

For GitHub deployment, add `PRODUCT_BROWSING_API_KEY` in repository Settings â†’
Secrets and variables â†’ Actions. The deployment workflow uploads it as a
Cloudflare Worker secret alongside the existing Shopify secrets. `wrangler.jsonc`
declares it required. Set the same header in WhatChimp's trusted HTTP integration.
Shopify Admin credentials remain exclusively on the backend. Never send them to
WhatChimp or WhatsApp users. Authentication is applied to the new browsing routes;
existing routes retain their behavior. Keep legacy administrative catalog routes
behind your existing trusted gateway; do not use them for customer browsing.

Only fixed GraphQL documents run, with user inputs passed as variables. No
metafields, ratings, reviews, or sensitive administrative fields are returned.
Logs contain error categories only, never credentials or upstream error text.

## Endpoints and input rules

All paths below have prefix `/api/v1/shopify`. All require `X-API-Key`.
IDs accept a positive numeric Shopify resource ID or the matching Shopify GID;
The collections-list response uses numeric ID strings for real collection rows
and `PAGE:<number>` for navigation rows. Other resource responses use GIDs. Wrong resource types, malformed IDs, and zero/negative
IDs return 422. Use query aliases for GIDs to avoid slash encoding problems.

| Method and path | Inputs | Response model |
| --- | --- | --- |
| GET `/products/collections` | `page=1` (positive integer) | `MenuCollections` |
| GET `/products/collections/{collection_id}/products` | `limit=10` (1â€“50), optional `cursor` | `CollectionProducts` |
| GET `/products/collection-products` | Required `collection_id`; same limit/cursor | Same collection response; recommended for GIDs |
| GET `/products/{product_id}` | Optional `collection_id` context | `ProductDetails` |
| GET `/products/details` | Required `product_id`; optional `collection_id` | Same details response; recommended for GIDs |

`cursor` is an opaque Shopify cursor (1â€“2048 characters); pass it back unchanged.
Query IDs have a 100-character bound. Do not add `menu_id`: the menu is fixed.
Swagger/OpenAPI documents inputs, response models, API-key security, and errors.

## Menu filtering and access rules

- Traverse all three supported Shopify navigation levels in depth-first menu order.
- Include only `COLLECTION` links with a valid Collection `resourceId` GID.
- Deduplicate by GID, preserving the first link's label, URL, tags, and position.
  A later unfiltered duplicate never overrides an earlier tagged link.
- Keep the menu item's customer-facing title, even when Shopify's collection title differs.
- GET `/products/collections?page=1` returns up to 9 unique valid collections
  in depth-first menu order. All collections are reachable through successive pages.
  `total` counts all unique menu collections, `page` is the requested page.
- When another page exists, `has_next` is true and the tenth, final entry in
  `collections` is `{"id": "PAGE:2", "title": "More Categories ?"}` (using the next
  page number). Navigation rows contain only `id` and `title` and are not Shopify
  collections. `total` excludes navigation rows. There is no separate `more` field.
- On the last page `has_next` is false and no navigation row is appended. An empty
  menu or page beyond the end returns `collections: []` and `has_next: false`.
  Invalid page inputs return 422. Real collections retain their URL and tag fields.
- Product access checks use the full configured menu and preserve tag restrictions.
- Never query all Shopify collections to discover menu options.
- Preserve menu tags. Every tag on the first link must occur in product `tags`
  (case-insensitive exact tag matching, AND semantics). Filtering occurs locally
  while scanning that collection in its default Shopify order. No tagged link is
  silently broadened into an unfiltered collection.
- A missing menu returns 502 `menu_unavailable`. An existing empty menu returns
  200 with `total: 0` and `collections: []`.
- A selected collection must be in the current menu before products are queried.
  Missing/disallowed collections return 404 with the same safe message.
- Details with `collection_id` must match that allowed collection and its tags.
  Without context, paginate only the selected product's collection memberships
  and require intersection with at least one allowed, tag-matching menu collection.
  There is no unrestricted root collection-list query.

## Product visibility, prices, and pagination

Products must have status `ACTIVE` and a non-null absolute HTTPS `onlineStoreUrl`.
Shopify documents null as not published to the Online Store. Draft, archived,
unlisted, and unpublished products are excluded. This is Online Store publication
visibility, not customer/market-specific catalog eligibility or store-password access.
Out-of-stock products can be displayed, with truthful variant availability.

Images use HTTPS Shopify CDN URLs or null; image data is never downloaded.
`image_alt` is Shopify's alt text. Each product returns a full sanitized
`description`, a single decimal-string `price`, and separate `currency`.
There is no nested min/max price payload. The display price comes from the first
available variant in Shopify's default variant order, falling back to the first
variant only when all are unavailable. This follows the standard default product
selection documented by [Shopify Liquid](https://shopify.dev/docs/api/liquid/objects/product#product-selected_or_first_available_variant).
`variant_id` is the real Shopify ProductVariant GID of that selected variant
(e.g. `gid://shopify/ProductVariant/444`), returned alongside its selling price
for downstream ordering. It is read from Shopify, never derived from a product ID.
If all variants are sold out, it identifies the first variant used for pricing;
it does not guarantee availability or place an order.
`compare_at_price` comes from that same variant and is returned only if strictly
higher than its selling price; `on_sale` reflects that comparison. Other variant
prices remain in details. Values never use binary floating point.
This is the shop-currency default price, not a promise to reproduce custom theme
scripts, selected URL variants, market conversion, cart discounts, or customer
pricing. Verify a concrete product URL if the theme differs. Do not scrape or
invent a discount. PKR is formatted as Rs. in WhatsApp only when Shopify confirms
PKR; other currencies retain their currency code.

Collection responses request up to 10 raw products per Shopify call, each with
up to 50 variants for default price selection, to bound nested GraphQL cost. Scan
up to 10 pages to fill the requested 1â€“50 visible products. Preserve Shopify order.
The cursor follows the last scanned page, including filtered products; none are
silently skipped. At the scan limit, return a possibly short/empty page with a
continuation cursor if Shopify has more data. Clients must follow pagination even
after an empty page when `has_next_page` is true. No total product count is invented.
If the first 50 variants have none available, listing follows variant pages
until the first available is found or all variants are exhausted, bounded by
20 pages per product. Exceeding that bound returns 503 rather than a guessed price.

Details load variants in pages of 50, up to 1,000 variants (20 pages); exceeding
this returns 503 `lookup_limit`, never silently truncated details. Membership
checks without context similarly scan up to 20 pages of 50 memberships and fail
closed with 503 when a match cannot be determined within the limit. Supply context
to avoid this scan. Invalid/non-advancing upstream cursors return 502.

HTTP timeouts use the existing 20-second client setting. Browsing opts into at
most three attempts for network failures, HTTP 429/5xx, or GraphQL THROTTLED.
Backoff starts at 0.5 then 1 second, increased by numeric Retry-After or Shopify
cost/throttle restoration information. If the required wait exceeds 5 seconds,
fail immediately rather than retry early. Permission, authentication, and other
GraphQL errors are not retried. Existing order/client calls keep their behavior.

## Response fields and examples

Examples use illustrative IDs, prices, titles, and URLs, not verified store data.

```http
GET /api/v1/shopify/products/collections
X-API-Key: YOUR_BACKEND_KEY
```

```json
{
  "menu_id": "gid://shopify/Menu/235088314461",
  "menu_title": "Shop",
  "total": 1,
  "collections": [{"id": "111", "title": "Hair Care", "url": "/collections/hair-care", "tags": []}],
  "page": 1,
  "has_next": false
}
```

```http
GET /api/v1/shopify/products/collections/111/products?limit=10
GET /api/v1/shopify/products/collection-products?collection_id=gid%3A%2F%2Fshopify%2FCollection%2F111&limit=10
X-API-Key: YOUR_BACKEND_KEY
```

```json
{
  "collection_id": "gid://shopify/Collection/111",
  "collection_title": "Hair Care",
  "products": [{
    "id": "gid://shopify/Product/333", "variant_id": "gid://shopify/ProductVariant/444", "title": "Conditioner", "handle": "conditioner",
    "image_url": null, "image_alt": null,
    "description": "Description from Shopify.",
    "price": "10.00", "currency": "USD",
    "compare_at_price": "15.00", "on_sale": true,
    "product_url": "https://example.com/products/conditioner"
  }],
  "pagination": {"has_next_page": false, "next_cursor": null}
}
```

```http
GET /api/v1/shopify/products/333?collection_id=111
GET /api/v1/shopify/products/details?product_id=gid%3A%2F%2Fshopify%2FProduct%2F333&collection_id=111
X-API-Key: YOUR_BACKEND_KEY
```

```json
{
  "id": "gid://shopify/Product/333", "variant_id": "gid://shopify/ProductVariant/444", "title": "Conditioner", "handle": "conditioner",
  "image_url": null, "image_alt": null,
  "description": "Description from Shopify.",
    "price": "10.00", "currency": "USD",
  "compare_at_price": "15.00", "on_sale": true,
  "product_url": "https://example.com/products/conditioner",
  "vendor": "Dr Elements", "product_type": "Conditioner",
  "available": true,
  "variants": [{"id": "gid://shopify/ProductVariant/444", "title": "250ML", "price": "10.00", "compare_at_price": "15.00", "available": true, "selected_options": [{"name": "Size", "value": "250ML"}]}],
  "whatsapp_message": "Conditioner\n\nPrice: USD 10\n\nOriginal Price: USD 15\n\nDescription:\nDescription from Shopify.\n\nAvailable Options:\nâ€¢ 250ML: USD 10\n\nView Product:\nhttps://example.com/products/conditioner"
}
```

All fields shown in a response model are returned, with nullable values as null.
`available` means at least one variant is available for sale. `selected_options`
preserve Shopify name/value pairs; variant prices use the product's shop currency.

## WhatsApp formatting

Use Shopify HTML description when present, otherwise its plain description.
Standard-library HTML parsing removes scripts/styles/templates and tags,
decodes entities, and normalizes whitespace. Raw HTML is never used as the message.
Both list and detail responses retain the full sanitized Shopify description.
The WhatsApp message includes that full description without truncation or an
added ellipsis. Empty descriptions omit that paragraph. Use short paragraphs,
currency labels, one default selling price, and plain Unicode bullets. The bot
integration must split long messages to its actual WhatsApp/WhatChimp limits;
this backend does not silently discard product information. Theme-only sections
or metafields are not fabricated or fetched as unrestricted sensitive data.
List at most 10 available variant titles with their prices; advertise more options
on the product page when needed. Unavailable variants remain in structured data
but never in Available Options. With none available, say Out of stock.
Always include the canonical Online Store URL. Do not invent ingredients,
benefits, usage instructions, medical claims, reviews, stars, or availability.

## Errors

All errors are curated JSON, e.g.
`{"success": false, "code": "not_found", "message": "This product or collection is not available in the shop menu."}`.
No upstream exception text, credentials, or internal GraphQL details are exposed.

| HTTP | Codes / meaning |
| --- | --- |
| 401 | `unauthorized`: missing/wrong X-API-Key |
| 404 | `not_found`: resource missing, invisible, outside menu, or tag mismatch |
| 422 | `invalid_id`, `invalid_limit`, `invalid_request`: fix inputs |
| 502 | `menu_unavailable`, `invalid_upstream_response`, `shopify_unavailable`: configuration, permission, timeout, throttle, HTTP or GraphQL failure |
| 503 | `configuration_error`, `lookup_limit`: missing server config or bounded lookup exceeded |
| 500 | `internal_error`: unexpected error, safe retry message |

## Test locally and through Swagger

1. Run `uv sync --all-groups` and fill `.env` from `.env.example`, including the key.
2. Run `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
3. Open `http://127.0.0.1:8000/docs`, click Authorize, and enter your browsing key.
4. Under Product browsing, execute collections. Copy a returned ID, then call
   collection-products. Copy a product ID into details and optionally pass the
   collection ID. Inspect structured fields and `whatsapp_message`.
5. For automated offline tests run `uv run pytest -q`. Focused checks:
   `uv run pytest tests/test_product_browsing.py tests/test_product_client.py -q`.
   Responses and HTTP transport are mocked; no real Shopify access is needed.

## WhatChimp integration guide

Step A â€” Product Information: call GET `/api/v1/shopify/products/collections`.
Map `collections[].title` to selectable labels and `collections[].id` to stored values.

Step B â€” Collection Selected: call GET
`/api/v1/shopify/products/collections/{collection_id}/products` with a numeric ID,
or use `/products/collection-products?collection_id=ENCODED_GID` (recommended).
Display `products[].title`, the single `price` with `currency`, and `image_url` where
supported. Store the selected product ID and collection ID. Implement Next from
`pagination.next_cursor` whenever `has_next_page` is true.

Step C â€” Product Selected: call GET `/api/v1/shopify/products/{product_id}` or
`/products/details?product_id=ENCODED_GID&collection_id=ENCODED_COLLECTION_GID`.
Display `whatsapp_message`. Include X-API-Key privately on every HTTP request.
Map curated error messages to a retry/support response.

Verify WhatChimp's actual interactive message capabilities, dynamic list
generation, option limits, image support, HTTP headers, URL encoding, pagination,
and JSON response mapping before configuring the final flow. Backend output alone
does not establish those platform capabilities. No WhatChimp flows are modified.

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

## WhatChimp collection pagination

Start each Product Information journey with `page=1`. Render the returned
`collections` array directly as list rows using each entry's `id` and `title`.
When `has_next` is true, the array already includes More Categories ? as the
last (tenth) row. Do not append another navigation row.

When the selected ID starts with `PAGE:`, extract its positive integer suffix
(e.g. `PAGE:2` means page 2) and call
`/api/v1/shopify/products/collections?page=2` with the same X-API-Key. Replace the
list with the new response. Otherwise pass the selected numeric Shopify collection ID
to the collection-products endpoint. Navigation IDs are not collection IDs and
are rejected by product lookup validation. Reset to page 1 when restarting.

The selected row carries the counter, so no shared backend counter is needed.
Any stored page variable must belong to the individual conversation. Requests
are stateless and repeating a page returns the same batch while the menu is
unchanged. The current menu is loaded for each request: edits/reordering can move
collections between pages, so restart at page 1 after edits.
For example, 23 unique collections yield 9 + More, 9 + More, then 5 without More.
WhatChimp selection routing must be configured separately.

## Interactive WhatChimp product cards

POST `/api/whatsapp/product-card` reuses this browsing service to submit one
interactive product card, protected by a separate inbound key. See
[whatsapp-product-card.md](whatsapp-product-card.md) for its complete contract,
settings, examples, WhatChimp HTTP block setup, limits, and unverified API details.
Existing browsing responses and access rules remain unchanged.
