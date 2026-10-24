from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.api import product_card as route
from app.core.config import WhatChimpSettings
from app.schemas.product_card import ProductCardRequest, CardError
from app.schemas.product_browsing import ProductDetails, BrowsingError
from app.services.product_card import ProductCardService
from app.clients.whatchimp_client import WhatChimpClient
from app.messaging.product_card_formatter import build_product_card

SETTINGS = WhatChimpSettings("private-token", "12345", "inbound-secret")


def product(**changes):
    data = dict(id="gid://shopify/Product/123", variant_id="gid://shopify/ProductVariant/456",
        title="Lotion", handle="lotion", description="<p>Moisturizing lotion.</p>",
        price="2950.00", currency="PKR", compare_at_price="3500.00", on_sale=True,
        product_url="https://example.com/lotion", image_url="https://cdn.shopify.com/a.jpg",
        vendor="Dr Elements", product_type="Lotion", available=True, variants=[], whatsapp_message="")
    data.update(changes)
    return ProductDetails(**data)


def request(**changes):
    return ProductCardRequest(**(dict(phone_number="923001234567", product_id="123") | changes))


@pytest.mark.parametrize("identifier", ["123", "gid://shopify/Product/123"])
async def test_selected_product_uses_real_details_and_media_api(identifier):
    source = SimpleNamespace(product_details=AsyncMock(return_value=product()), collection_products=AsyncMock())
    seen = []
    def handler(req):
        seen.append(req)
        assert req.url.path == "/api/v1/whatsapp/send/file"
        fields = parse_qs(req.content.decode())
        assert fields["apiToken"] == ["private-token"]
        assert fields["phone_number"] == ["923001234567"]
        assert fields["media_url"] == ["https://cdn.shopify.com/a.jpg"]
        assert fields["media_type"] == ["image"]
        assert "https://example.com/lotion" in fields["media_caption_text"][0]
        assert "buttons" not in fields and "media_name" not in fields
        return httpx.Response(200, json={"status":"1"})
    result = await ProductCardService(source, WhatChimpClient(SETTINGS, httpx.MockTransport(handler))).submit(request(product_id=identifier))
    source.product_details.assert_awaited_once_with("gid://shopify/Product/123")
    source.collection_products.assert_not_awaited()
    assert result.success and result.product.on_sale and result.product.product_url == "https://example.com/lotion"
    assert "collection_id" not in result.model_dump() and len(seen) == 1


def test_professional_caption():
    card = build_product_card(product())
    text = card["message"]
    assert "*Lotion*" in text and "*Current price:* PKR 2,950" in text
    assert "*On sale:* Yes" in text and "PKR 3,500" in text
    assert "Moisturizing lotion." in text and "<p>" not in text
    assert "*Shop online*" in text and text.endswith("https://example.com/lotion")
    assert "buttons" not in card and "Product 1 of" not in text


@pytest.mark.parametrize("compare", [None, "2950", "1000"])
def test_no_sale_uses_same_variant_comparison(compare):
    text = build_product_card(product(compare_at_price=compare, on_sale=True))["message"]
    assert "*On sale:* No" in text and "Original price" not in text


def test_long_caption_keeps_link_and_price():
    text = build_product_card(product(description="x" * 5000))["message"]
    assert len(text) <= 1024 and text.endswith("https://example.com/lotion") and "PKR 2,950" in text


async def test_no_image_falls_back_to_single_text_send():
    calls=[]
    def handler(req):
        calls.append(req)
        assert req.url.path == "/api/v1/whatsapp/send"
        assert "media_url" not in parse_qs(req.content.decode())
        return httpx.Response(200,json={"status":1})
    source=SimpleNamespace(product_details=AsyncMock(return_value=product(image_url=None, available=False)))
    await ProductCardService(source,WhatChimpClient(SETTINGS,httpx.MockTransport(handler))).submit(request())
    assert len(calls)==1


@pytest.mark.parametrize("code,body,error", [(401,{},"whatchimp_authentication"),(403,{},"whatchimp_authentication"),
    (429,{},"whatchimp_rate_limit"),(500,{},"whatchimp_rejected"),(200,{"status":"0"},"whatchimp_rejected"),
    (200,{"status":True},"whatchimp_rejected"),(200,[],"whatchimp_rejected")])
async def test_provider_failure_no_retry_or_secret(code,body,error):
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(code,json=body)
    client=WhatChimpClient(SETTINGS,httpx.MockTransport(handler))
    with pytest.raises(CardError) as exc:
        await client.send_card("923001234567",build_product_card(product()))
    assert exc.value.code==error and len(calls)==1
    assert "private-token" not in repr(client.last_diagnostics)+str(exc.value)


@pytest.mark.parametrize("error", [httpx.ReadTimeout,httpx.ConnectError])
async def test_transport_error_no_retry(error):
    calls=[]
    def handler(req):
        calls.append(req)
        raise error("private-token",request=req)
    with pytest.raises(CardError):
        await WhatChimpClient(SETTINGS,httpx.MockTransport(handler)).send_card("923001234567",build_product_card(product()))
    assert len(calls)==1


async def test_invalid_provider_json():
    with pytest.raises(CardError):
        await WhatChimpClient(SETTINGS,httpx.MockTransport(lambda req:httpx.Response(200,text="private-token"))).send_card("923001234567",build_product_card(product()))


@pytest.mark.parametrize("changes", [{"product_id":"bad"},{"product_id":"gid://shopify/Collection/1"},
    {"phone_number":"+923001234567"},{"phone_number":"hello"},{"collection_id":"111"},{"product_index":0}])
def test_request_validation(changes):
    with pytest.raises(ValidationError):
        request(**changes)


async def test_not_found_never_sends():
    sender=SimpleNamespace(send_card=AsyncMock())
    source=SimpleNamespace(product_details=AsyncMock(side_effect=BrowsingError(404,"not_found","Unavailable")))
    with pytest.raises(BrowsingError):
        await ProductCardService(source,sender).submit(request())
    sender.send_card.assert_not_awaited()


@pytest.mark.parametrize("value", ["NaN","Infinity","-1","bad"])
def test_invalid_price(value):
    with pytest.raises(CardError):
        build_product_card(product(price=value))


def test_endpoint_auth_validation_and_send(monkeypatch,caplog):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY","inbound-secret")
    monkeypatch.setenv("WHATCHIMP_API_TOKEN","private-token")
    monkeypatch.setenv("WHATCHIMP_PHONE_NUMBER_ID","12345")
    source=SimpleNamespace(product_details=AsyncMock(return_value=product()))
    sender=SimpleNamespace(send_card=AsyncMock())
    monkeypatch.setattr(route,"get_shopify_service",lambda request:SimpleNamespace(client=None))
    monkeypatch.setattr(route,"ProductBrowsingService",lambda client:source)
    monkeypatch.setattr(route,"WhatChimpClient",lambda settings:sender)
    client=TestClient(app)
    assert client.post("/api/whatsapp/product-card",json=request().model_dump()).status_code==401
    headers={"X-API-Key":"inbound-secret"}
    result=client.post("/api/whatsapp/product-card",json=request().model_dump(),headers=headers)
    assert result.status_code==200 and result.json()["product"]["on_sale"]
    sender.send_card.assert_awaited_once()
    source.product_details.side_effect=ValueError("private-token 923001234567")
    result=client.post("/api/whatsapp/product-card",json=request().model_dump(),headers=headers)
    assert result.status_code==502
    assert "private-token" not in result.text+caplog.text and "923001234567" not in result.text+caplog.text
    result=client.post("/api/whatsapp/product-card",json={"phone_number":"+923001234567","product_id":"123"},headers=headers)
    assert result.status_code==422 and "923001234567" not in result.text
