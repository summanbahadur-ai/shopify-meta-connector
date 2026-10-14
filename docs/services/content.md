# Policies, pages, and FAQ

## Purpose and implementation

Read Shopify store content for later use by an assistant.
Routes: `app/api/v1/shopify.py`. Methods and query constants:
`app/services/shopify_service.py`. Shared calls/errors: [shared.md](shared.md).
Existing basic tests: `tests/test_shopify_service.py::test_policies_and_pages`.

## Policies

GET `/api/v1/shopify/policies` -> `get_policies()`. No query parameters.
Calls GraphQL `Policies` without variables. Selects:

```text
shop { shopPolicies { id title type body url createdAt updatedAt } }
```

Upstream inner data is `{"shop": {"shopPolicies": [<policy objects>]}}`.
Service returns the policy list; HTTP route wraps it in
`{"policies": [<policy objects>]}` with HTTP 200. Empty list becomes
`{"policies": []}`. HTML in `body` is returned unchanged.

## Pages

GET `/api/v1/shopify/pages` -> `get_pages(limit=50, after=None, query=None)`.

| Query input | Default | Rule |
| --- | --- | --- |
| `limit` | 50 | Integer 1..100; invalid values return HTTP 422 |
| `after` | null | Optional Shopify cursor |
| `query` | null | Optional Shopify search string, forwarded unchanged |

Direct service calls clamp limit to 1..100. Calls GraphQL `Pages` with variables
`{"first": limit, "after": after, "query": query}`. Selects:

```text
pages {
  nodes { id title handle body bodySummary isPublished createdAt updatedAt }
  pageInfo { hasNextPage endCursor }
}
```

Upstream data has `pages.nodes` and `pages.pageInfo`. Service and HTTP 200
response use `{"count": <page size>, "pages": [<page objects>],
"page_info": {"hasNextPage": <boolean>, "endCursor": <cursor or null>}}`.
Empty results return count 0 and pages []. HTML and published flags are passed
through; the service does not filter unpublished results itself.

## FAQ search

GET `/api/v1/shopify/faq` accepts no query parameters. There is no separate
FAQ service method; the route calls
`get_pages(limit=50, query="title:FAQ OR handle:faq")` with no cursor.
The Shopify operation and returned shape are exactly the Pages behavior above.

FAQ is a page search, not an AI answer or a structured question/answer parser.
It returns only the first page of matches. All operations use shared errors.

## Acceptance checks for changes

Check policy HTTP wrapping versus service return value, page fields, cursor
and query forwarding, empty results, and the exact FAQ search variables.
Existing tests cover basic service counts, not HTTP wrappers or FAQ behavior.

## Requested change

None pending.
