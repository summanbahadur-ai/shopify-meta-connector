# Policies and FAQ

## Purpose and implementation

Read Shopify store content for later use by an assistant.
Routes: `app/api/v1/shopify.py`. Methods and query constants:
`app/services/shopify_service.py`. Shared calls/errors: [shared.md](shared.md).
Existing basic tests: `tests/test_shopify_service.py::test_policies_and_pages`.

## Policies

GET `/api/v1/shopify/policies` -> `get_policies(policy_type=None)`.
Optional query parameter `policy_type` filters the returned list by an exact,
case-sensitive match against the Shopify policy's `type`. Omitting it returns
all policies; unknown, empty or differently cased values return an empty list.
Filtering is local after the existing Shopify lookup; the GraphQL query is unchanged.

Example: `/api/v1/shopify/policies?policy_type=REFUND_POLICY` returns only refund
policies. `/api/v1/shopify/policies?policy_type=SHIPPING_POLICY` selects shipping
policies when that type is present. The response remains `{"policies": [...]}`.
Calls GraphQL `Policies` without variables. Selects:

```text
shop { shopPolicies { id title type body url createdAt updatedAt } }
```

Upstream inner data is `{"shop": {"shopPolicies": [<policy objects>]}}`.
Service returns the policy list; HTTP route wraps it in
`{"policies": [<policy objects>]}` with HTTP 200. Empty list becomes
`{"policies": []}`. `body` is converted to readable plain text by
`app/messaging/policy_formatter.py::policy_html_to_text`. Paragraphs and headings
are separated with blank lines; line breaks, bullet lists and numbered lists
remain readable. HTML entities are decoded, script/style/template content and
comments are omitted, and safe HTTP(S), email and telephone link targets are
retained beside their labels. Policy wording is not summarized or truncated.
Empty/null bodies become an empty string. Other policy fields and filtering
remain unchanged; upstream objects are copied rather than mutated. FAQ/page HTML
is unaffected.

Example: `<h2>Returns</h2><p>Keep your receipt.</p>` becomes
`Returns\n\nKeep your receipt.` in the JSON body field. JSON escapes the newlines;
the consuming application should display the decoded string.

## Internal page lookup

`get_pages(limit=50, after=None, query=None)` supports FAQ search internally;
it has no general-purpose public endpoint.

| Service input | Default | Rule |
| --- | --- | --- |
| `limit` | 50 | Integer clamped to 1..100 |
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

Upstream data has `pages.nodes` and `pages.pageInfo`. The service returns `{"count": <page size>, "pages": [<page objects>],
"page_info": {"hasNextPage": <boolean>, "endCursor": <cursor or null>}}`.
Empty results return count 0 and pages []. HTML and published flags are passed
through; the service does not filter unpublished results itself.

## FAQ search

GET `/api/v1/shopify/faq` accepts no query parameters. There is no separate
FAQ service method; the route calls
`get_pages(limit=50, query="title:FAQ OR handle:faq")` with no cursor.
The Shopify operation and HTTP 200 response use the internal page lookup shape above.

FAQ is a page search, not an AI answer or a structured question/answer parser.
It returns only the first page of matches. All operations use shared errors.

## Acceptance checks for changes

Check policy HTTP wrapping versus service return value, page fields, cursor
and query forwarding, empty results, and the exact FAQ search variables.
Tests cover policy filtering, exact-match and empty-result behavior, unchanged HTML,
and the HTTP response wrapper, alongside basic connection/page checks.

