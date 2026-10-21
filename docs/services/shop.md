# Shopify connection test

## Purpose and implementation

Verify Shopify connectivity, including store metadata in the connection result.
Routes: `app/api/v1/shopify.py`; methods and `SHOP_QUERY`:
`app/services/shopify_service.py`. Shared calls/errors: [shared.md](shared.md).
Existing basic connection test: `tests/test_shopify_service.py::test_connection`.

## Inputs and operations

| Public GET endpoint | Service method | Input |
| --- | --- | --- |
| `/api/v1/shopify/connection` | `get_connection_status()` | No query parameters |

The connection check uses the configured store credentials and calls the Shopify GraphQL
`ShopConnection` operation, with no variables. It selects:

```text
shop { name myshopifyDomain primaryDomain { host url }
       currencyCode timezoneAbbreviation }
```

## Upstream and returned responses

Upstream data is `{"shop": {<selected fields>}}`.
`get_connection_status()` and `/connection` return:

```json
{
  "connected": true,
  "shop": {
    "name": "Demo Store",
    "myshopifyDomain": "demo.myshopify.com",
    "primaryDomain": {"host": "demo.example", "url": "https://demo.example"},
    "currencyCode": "USD",
    "timezoneAbbreviation": "PDT"
  }
}
```

Success is HTTP 200. Failure raises a shared error; there is no
`{"connected": false}` response. `/health` only checks that the app is running
and does not make this Shopify call.

## Acceptance checks for changes

Verify the connection response shape, the selected Shopify fields, and authentication
failure behavior. The existing fake-client test covers only part of the payload.

