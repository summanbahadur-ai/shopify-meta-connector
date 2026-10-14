# Products and CSV export

## Purpose and implementation

Read a catalog page or download the catalog as CSV.
Routes and CSV generation: `app/api/v1/shopify.py`.
Methods and `PRODUCTS_QUERY`: `app/services/shopify_service.py`.
Shared calls/errors: [shared.md](shared.md).
Existing basic listing test: `tests/test_shopify_service.py::test_products`.

## List products

GET `/api/v1/shopify/products` -> `get_products(limit=50, after=None)`.

| Query input | Default | Rule |
| --- | --- | --- |
| `limit` | 50 | Integer 1 through 100; HTTP rejects other values with 422 |
| `after` | null | Optional Shopify cursor string |

Direct service calls clamp limit to 1..100. The Shopify GraphQL operation is
`Products`, variables `{"first": limit, "after": after}`. Upstream inner data:

```text
products {
  nodes [{ id, title, handle, descriptionHtml, vendor, productType, status, tags,
    featuredMedia: { preview: { image: { url, altText } } },
    variants: { nodes: [{ id, title, sku, barcode, price, compareAtPrice }] }
  }]
  pageInfo { hasNextPage, endCursor }
}
```

The query requests the first 100 variants per product. The service returns
HTTP 200 JSON with the same product objects, but a different outer wrapper:

```json
{
  "count": 0,
  "products": [],
  "page_info": {"hasNextPage": false, "endCursor": null}
}
```

`count` is the number on this page, not the catalog total. Pass `endCursor`
as `after` to fetch the next page when `hasNextPage` is true.

## Export products

GET `/api/v1/shopify/products/export.csv` accepts no query parameters and calls
`get_all_products()`. That method repeatedly calls `get_products(limit=100)`
with each next cursor until `hasNextPage` is false, returning a list of products.
The route converts the list into CSV, one row per returned variant. A product
with no returned variants gets one row with empty variant fields.

HTTP 200, content type `text/csv`, attachment filename
`shopify-product-catalog.csv`. Exact header order:

```text
product_id,title,handle,vendor,product_type,status,variant_id,variant_title,sku,barcode,price,compare_at_price
```

Product fields map from `id`, `title`, `handle`, `vendor`, `productType`, `status`;
variant fields map from `id`, `title`, `sku`, `barcode`, `price`, `compareAtPrice`.
An empty catalog returns the header alone. All product pages and the CSV are
collected in memory before the response is sent. Variant pagination is not
implemented: products with over 100 variants have an incomplete variant export.
Shared upstream errors apply to both operations.

## Acceptance checks for changes

Check limit validation, cursor variables, empty pages, multiple product pages,
CSV quoting/header order, and products without variants. The existing test only
checks listing count; it does not cover CSV or multi-page export.

## Requested change

None pending.
