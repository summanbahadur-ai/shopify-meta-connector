from app.messaging.product_card_formatter import build_product_card
from app.schemas.product_browsing import ProductSummary


def product(**changes):
    data = dict(id="gid://shopify/Product/123", variant_id="gid://shopify/ProductVariant/456",
                title="Lotion", handle="lotion", description="<p>Moisturizing lotion.</p>",
                price="2950.00", currency="PKR", product_url="https://example.com/lotion")
    data.update(changes)
    return ProductSummary(**data)


def test_card_format_and_buttons():
    card = build_product_card(product(), 0, 2, collection_id="111")
    assert "PKR 2,950" in card["message"]
    assert "Product 1 of 2" in card["message"]
    assert card["message"] == "*Lotion*\n\nPrice: PKR 2,950\n\nProduct 1 of 2"
    assert card["buttons"] == [{"id": "DETAILS:123", "title": "View Details"},
                               {"id": "ADD:123", "title": "Add to Cart"},
                               {"id": "NEXT:111:1", "title": "Next Product"}]


import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import product_card as route
from app.clients.whatchimp_client import WhatChimpClient
from app.core.config import WhatChimpSettings
from app.schemas.product_card import ProductCardRequest, CardError
from app.services.product_card import ProductCardService


SETTINGS = WhatChimpSettings("private-token", "12345", "inbound-secret")


def details(**changes):
    result = product(**changes)
    return SimpleNamespace(**result.model_dump(), variants=[SimpleNamespace(id=result.variant_id, available=True)],
                           model_dump=result.model_dump)


def browsing(products=None, **changes):
    batch = SimpleNamespace(products=[product()] if products is None else products,
                            pagination=SimpleNamespace(has_next_page=False, next_cursor=None))
    result = SimpleNamespace(collection_products=AsyncMock(return_value=batch),
                             product_details=AsyncMock(return_value=details()))
    for key, value in changes.items():
        setattr(result, key, value)
    return result


def request(**changes):
    data = dict(phone_number="923001234567", collection_id="111")
    data.update(changes)
    return ProductCardRequest(**data)


@pytest.mark.parametrize("collection", ["111", "gid://shopify/Collection/111"])
async def test_success_submission(collection):
    seen = []
    def handler(req):
        seen.append(req)
        fields = parse_qs(req.content.decode())
        assert req.headers["content-type"].startswith("application/x-www-form-urlencoded")
        assert fields["apiToken"] == ["private-token"]
        assert json.loads(fields["buttons"][0])[0]["id"] == "DETAILS:123"
        assert "media_url" not in fields
        assert "button_header_text" in fields
        return httpx.Response(200, json={"status": "1", "message": "Accepted", "wa_message_id": "example"})
    client = WhatChimpClient(SETTINGS, httpx.MockTransport(handler))
    result = await ProductCardService(browsing(), client).submit(request(collection_id=collection))
    assert result.success and result.collection_id == "111"
    assert result.product.variant_id == "gid://shopify/ProductVariant/456"
    assert len(seen) == 1


@pytest.mark.parametrize("status,body,expected", [
    (401, {"message": "private-token"}, "whatchimp_authentication"),
    (403, {}, "whatchimp_authentication"), (429, {}, "whatchimp_rate_limit"),
    (500, {}, "whatchimp_rejected"), (200, {"status": "0"}, "whatchimp_rejected"),
    (200, {"success": True}, "whatchimp_rejected"), (200, [], "whatchimp_rejected"),
    (200, {"status": True}, "whatchimp_rejected"),
])
async def test_upstream_failures_no_retry_or_secrets(status, body, expected):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json=body)
    client = WhatChimpClient(SETTINGS, httpx.MockTransport(handler))
    with pytest.raises(CardError) as exc:
        await client.send_card("923001234567", build_product_card(product(), 0, 1))
    assert exc.value.code == expected
    assert "private-token" not in str(exc.value)
    assert "private-token" not in repr(client.last_diagnostics)
    assert len(calls) == 1


@pytest.mark.parametrize("error,code", [(httpx.ReadTimeout, "whatchimp_timeout"), (httpx.ConnectError, "whatchimp_connection")])
async def test_transport_errors(error, code):
    calls = []
    def handler(req):
        calls.append(req)
        raise error("private-token", request=req)
    with pytest.raises(CardError) as exc:
        await WhatChimpClient(SETTINGS, httpx.MockTransport(handler)).send_card("923001234567", build_product_card(product(), 0, 1))
    assert exc.value.code == code and len(calls) == 1
    assert "private-token" not in str(exc.value)


async def test_invalid_json():
    client = WhatChimpClient(SETTINGS, httpx.MockTransport(lambda req: httpx.Response(200, text="private-token")))
    with pytest.raises(CardError) as exc:
        await client.send_card("923001234567", build_product_card(product(), 0, 1))
    assert exc.value.code == "whatchimp_rejected"
    assert "private-token" not in repr(client.last_diagnostics)


def test_image_description_omitted_and_last_navigation():
    card = build_product_card(product(image_url="https://cdn.shopify.com/a.jpg", description="<p>" + "x" * 600 + "</p>"), 1, 2)
    assert card["media_url"] == "https://cdn.shopify.com/a.jpg"
    assert "button_header_text" not in card
    assert len(card["message"]) < 1024
    assert card["buttons"][-1] == {"id": "CATEGORIES:1", "title": "Back to Categories"}
    assert all(len(b["title"]) <= 20 and len(b["id"]) <= 256 for b in card["buttons"])


@pytest.mark.parametrize("products,index,code", [([], 0, "empty_collection"), ([product()], 1, "product_index_out_of_range")])
async def test_collection_boundaries(products, index, code):
    sender = SimpleNamespace(send_card=AsyncMock())
    with pytest.raises(CardError) as exc:
        await ProductCardService(browsing(products), sender).submit(request(product_index=index))
    assert exc.value.code == code
    sender.send_card.assert_not_awaited()


async def test_collection_pagination_exact_total_and_next_context():
    source = browsing()
    source.collection_products.side_effect = [
        SimpleNamespace(products=[], pagination=SimpleNamespace(has_next_page=True, next_cursor="a")),
        SimpleNamespace(products=[product(), product(id="gid://shopify/Product/789")], pagination=SimpleNamespace(has_next_page=False, next_cursor=None))]
    sender = SimpleNamespace(send_card=AsyncMock())
    await ProductCardService(source, sender).submit(request())
    args = sender.send_card.call_args.args[1]
    assert "Product 1 of 2" in args["message"]
    assert args["buttons"][-1]["id"] == "NEXT:111:1"
    assert source.collection_products.call_args.kwargs["cursor"] == "a"


async def test_unavailable_variant():
    source = browsing()
    source.product_details.return_value.variants[0].available = False
    sender = SimpleNamespace(send_card=AsyncMock())
    with pytest.raises(CardError) as exc:
        await ProductCardService(source, sender).submit(request())
    assert exc.value.code == "variant_unavailable"
    sender.send_card.assert_not_awaited()


async def test_scan_limit_never_sends(monkeypatch):
    monkeypatch.setattr("app.services.product_card.MAX_CARD_COLLECTION_PAGES", 1)
    source = browsing()
    source.collection_products.return_value.pagination = SimpleNamespace(has_next_page=True, next_cursor="a")
    sender = SimpleNamespace(send_card=AsyncMock())
    with pytest.raises(CardError) as exc:
        await ProductCardService(source, sender).submit(request())
    assert exc.value.code == "collection_limit"
    sender.send_card.assert_not_awaited()


@pytest.mark.parametrize("key", [None, "wrong"])
def test_inbound_key(monkeypatch, key):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "inbound-secret")
    response = TestClient(app).post("/api/whatsapp/product-card", json=request().model_dump(), headers={} if key is None else {"X-API-Key": key})
    assert response.status_code == 401


def test_missing_configuration(monkeypatch):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "inbound-secret")
    monkeypatch.delenv("WHATCHIMP_API_TOKEN", raising=False)
    response = TestClient(app).post("/api/whatsapp/product-card", json=request().model_dump(), headers={"X-API-Key": "inbound-secret"})
    assert response.status_code == 503 and response.json()["code"] == "configuration_error"


@pytest.mark.parametrize("changes", [{"phone_number": "+923001234567"}, {"phone_number": "hello"},
    {"phone_number": "0123456789"}, {"phone_number": "92300 1234567"}, {"product_index": -1},
    {"product_index": True}, {"collection_id": "PAGE:2"}, {"collection_id": "gid://shopify/Product/1"}])
def test_request_validation(changes):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        request(**changes)


def test_endpoint_success_and_safe_errors(monkeypatch, caplog):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "inbound-secret")
    monkeypatch.setenv("WHATCHIMP_API_TOKEN", "private-token")
    monkeypatch.setenv("WHATCHIMP_PHONE_NUMBER_ID", "12345")
    source = browsing()
    sender = SimpleNamespace(send_card=AsyncMock())
    # Preserve real authorization and service orchestration; only replace external clients.
    monkeypatch.setattr(route, "get_shopify_service", lambda request: SimpleNamespace(client=None))
    monkeypatch.setattr(route, "ProductBrowsingService", lambda client: source)
    monkeypatch.setattr(route, "WhatChimpClient", lambda settings: sender)
    client = TestClient(app)
    response = client.post("/api/whatsapp/product-card", json=request().model_dump(), headers={"X-API-Key": "inbound-secret"})
    assert response.status_code == 200 and response.json()["success"] is True
    source.collection_products.side_effect = ValueError("private-token 923001234567")
    response = client.post("/api/whatsapp/product-card", json=request().model_dump(), headers={"X-API-Key": "inbound-secret"})
    assert response.status_code == 502
    assert "private-token" not in response.text + caplog.text
    assert "923001234567" not in response.text + caplog.text


def test_validation_http_does_not_echo_contacts(monkeypatch):
    app.dependency_overrides[route.get_card_service] = lambda: None
    try:
        response = TestClient(app).post("/api/whatsapp/product-card", json={"phone_number": "+923001234567", "collection_id": "111"})
        assert response.status_code == 422
        assert "923001234567" not in response.text
    finally:
        app.dependency_overrides.pop(route.get_card_service, None)


def test_non_pkr_never_relabelled():
    with pytest.raises(CardError) as exc:
        build_product_card(product(currency="USD"), 0, 1)
    assert exc.value.code == "unsupported_currency"


async def test_real_shopify_service_with_mock_http(monkeypatch):
    from app.clients.shopify_client import ShopifyClient
    from app.core.config import Settings
    from app.services.product_browsing import ProductBrowsingService
    variant = {"id": "gid://shopify/ProductVariant/456", "title": "Default", "price": "2950.00",
               "compareAtPrice": None, "availableForSale": True, "selectedOptions": []}
    raw = {"id": "gid://shopify/Product/123", "title": "Lotion", "handle": "lotion", "status": "ACTIVE",
           "tags": [], "onlineStoreUrl": "https://example.com/lotion", "description": "Body lotion",
           "descriptionHtml": "", "featuredMedia": {"image": {"url": "https://cdn.shopify.com/a.jpg", "altText": "Lotion"}},
           "vendor": "Demo", "productType": "Lotion",
           "priceRangeV2": {"minVariantPrice": {"amount": "2950.00", "currencyCode": "PKR"},
                            "maxVariantPrice": {"amount": "2950.00", "currencyCode": "PKR"}},
           "variants": {"nodes": [variant], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    seen = []
    def handler(req):
        seen.append(req)
        if req.url.host == "app.whatchimp.com":
            fields = parse_qs(req.content.decode())
            assert fields["media_url"] == ["https://cdn.shopify.com/a.jpg"]
            return httpx.Response(200, json={"status": "1"})
        body = json.loads(req.content)
        query = body["query"]
        if "GetNavigationMenu" in query:
            data = {"menu": {"title": "Shop", "items": [{"type": "COLLECTION", "title": "Body", "resourceId": "gid://shopify/Collection/111"}]}}
        elif "GetCollectionProducts" in query:
            data = {"collection": {"title": "Body", "products": {"edges": [{"node": raw}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        elif "GetProductDetails" in query:
            data = {"product": raw}
        elif "ProductInCollection" in query:
            data = {"product": {"inCollection": True}}
        else:
            raise AssertionError("Unexpected query")
        return httpx.Response(200, json={"data": data})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(**{**kwargs, "transport": httpx.MockTransport(handler)}))
    shopify = ShopifyClient(Settings("demo.myshopify.com", "", "", shopify_access_token="private-shopify-token"))
    result = await ProductCardService(ProductBrowsingService(shopify), WhatChimpClient(SETTINGS)).submit(request())
    assert result.product.variant_id == variant["id"]
    assert sum(r.url.host == "app.whatchimp.com" for r in seen) == 1


async def test_missing_price_fails_before_send():
    source = browsing()
    source.collection_products.side_effect = KeyError("price")
    sender = SimpleNamespace(send_card=AsyncMock())
    with pytest.raises(KeyError):
        await ProductCardService(source, sender).submit(request())
    sender.send_card.assert_not_awaited()


def test_worker_config_precedence_and_safe_repr(monkeypatch):
    from starlette.requests import Request
    monkeypatch.setenv("WHATCHIMP_API_TOKEN", "local-secret")
    config = WhatChimpSettings.from_request(Request({"type": "http", "env": {
        "WHATCHIMP_API_TOKEN": "worker-secret", "WHATCHIMP_PHONE_NUMBER_ID": "123", "WHATCHIMP_INBOUND_API_KEY": "worker-key"}}))
    assert config.api_token == "worker-secret"
    assert "worker-secret" not in repr(config)
