from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.services.product_carousel import ProductCarouselService
from app.schemas.product_carousel import ProductCarouselRequest
from app.schemas.product_browsing import ProductSummary


def product(index=1, **changes):
    data = dict(id=f"gid://shopify/Product/{index}", variant_id=f"gid://shopify/ProductVariant/{index + 100}",
                title=f"Product {index}", handle=f"product-{index}", description="Not on the carousel",
                price="2950.00", currency="PKR", image_url="https://cdn.shopify.com/product.jpg",
                product_url=f"https://example.com/products/{index}")
    data.update(changes)
    return ProductSummary(**data)


def batch(products, cursor=None):
    return SimpleNamespace(products=products, pagination=SimpleNamespace(has_next_page=cursor is not None, next_cursor=cursor))


def browsing(*batches):
    async def details(identifier, context):
        index = int(identifier.rsplit("/", 1)[-1])
        result = product(index)
        return SimpleNamespace(**result.model_dump(), variants=[SimpleNamespace(id=result.variant_id, available=True)])
    return SimpleNamespace(collection_products=AsyncMock(side_effect=list(batches)), product_details=AsyncMock(side_effect=details))


async def test_prepare_four_shopify_cards_without_send():
    source = browsing(batch([product(i) for i in range(1, 5)], "next"))
    result = await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True))
    assert result.submitted is False and result.status == "prepared"
    assert len(result.cards) == 4
    assert result.pagination.next_cursor == "next"
    assert result.cards[0].variant_id == "gid://shopify/ProductVariant/101"
    assert result.cards[0].body == "Product 1\nPrice: PKR 2,950"
    assert result.cards[0].buttons[0].id == "DETAILS:1"


from app.schemas.product_card import CardError
from app.messaging.product_carousel_formatter import build_carousel_card
from fastapi.testclient import TestClient
from app.main import app
from app.api import product_carousel as route
from app.api import product_card as card_route
from pydantic import ValidationError


@pytest.mark.parametrize("limit", [2, 4, 10])
@pytest.mark.parametrize("collection", ["111", "gid://shopify/Collection/111"])
async def test_card_limits_and_id_forms(limit, collection):
    source = browsing(batch([product(i) for i in range(1, limit + 1)]))
    result = await ProductCarouselService(source).submit(ProductCarouselRequest(
        phone_number="923001234567", collection_id=collection, limit=limit, dry_run=True))
    assert result.count == limit and result.collection_id == "111"
    assert not result.pagination.has_next_page
    assert len({c.product_id for c in result.cards}) == limit
    assert all(len(c.buttons) == 2 for c in result.cards)


async def test_live_send_is_blocked_before_shopify_or_whatchimp():
    source = browsing()
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111"))
    assert exc.value.status == 501
    source.collection_products.assert_not_awaited()


async def test_filtered_empty_pages_and_continuation():
    source = browsing(batch([], "a"), batch([product(1), product(2)], "b"), batch([product(3), product(4)], "c"))
    result = await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True, cursor="start"))
    assert result.count == 4 and result.pagination.next_cursor == "c"
    assert source.collection_products.call_args_list[0].kwargs["cursor"] == "start"
    assert source.collection_products.call_args_list[-1].kwargs["limit"] == 2


async def test_image_missing_and_unavailable_variants_are_skipped():
    source = browsing(batch([product(1, image_url=None), product(2)]), batch([]))
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True))
    assert exc.value.code == "insufficient_carousel_products"
    assert source.product_details.await_count == 1
    source = browsing(batch([product(1), product(2)]))
    original = source.product_details.side_effect
    async def unavailable(identifier, context):
        details = await original(identifier, context)
        details.variants[0].available = False
        return details
    source.product_details.side_effect = unavailable
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True))
    assert exc.value.code == "insufficient_carousel_products"


@pytest.mark.parametrize("count", [0, 1])
async def test_at_least_two_cards_required(count):
    source = browsing(batch([product(i) for i in range(1, count + 1)]))
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True))
    assert exc.value.status == 422


async def test_duplicate_products_deduplicated_and_refilled():
    source = browsing(batch([product(1), product(1)], "a"), batch([product(2)]))
    result = await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True, limit=2))
    assert [c.product_id for c in result.cards] == ["gid://shopify/Product/1", "gid://shopify/Product/2"]


async def test_repeated_cursor_rejected():
    source = browsing(batch([], "start"))
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True, cursor="start"))
    assert exc.value.code == "invalid_pagination"


async def test_scan_budget(monkeypatch):
    monkeypatch.setattr("app.services.product_carousel.MAX_CAROUSEL_COLLECTION_PAGES", 1)
    source = browsing(batch([], "a"))
    with pytest.raises(CardError) as exc:
        await ProductCarouselService(source).submit(ProductCarouselRequest(phone_number="923001234567", collection_id="111", dry_run=True))
    assert exc.value.code == "collection_limit"


def test_body_limits_price_no_description_or_fake_currency():
    result = build_carousel_card(product(title="Long title " * 100))
    assert len(result.body) <= 160
    assert "PKR 2,950" in result.body
    assert "Not on the carousel" not in result.body
    assert all(len(b.title) <= 20 and len(b.id) <= 256 for b in result.buttons)
    with pytest.raises(CardError):
        build_carousel_card(product(currency="USD"))


@pytest.mark.parametrize("changes", [{"limit": 1}, {"limit": 11}, {"limit": True}, {"phone_number": "+923001234567"},
    {"collection_id": "PAGE:2"}, {"collection_id": "gid://shopify/Product/1"}, {"product_id": "1"},
    {"cursor": ""}, {"dry_run": "true"}])
def test_input_validation(changes):
    values = dict(phone_number="923001234567", collection_id="111", dry_run=True)
    values.update(changes)
    with pytest.raises(ValidationError):
        ProductCarouselRequest(**values)


@pytest.mark.parametrize("key", [None, "wrong"])
def test_http_authentication(monkeypatch, key):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "expected")
    response = TestClient(app).post("/api/whatsapp/product-carousel", json={"phone_number": "923001234567", "collection_id": "111", "dry_run": True}, headers={} if key is None else {"X-API-Key": key})
    assert response.status_code == 401


def test_endpoint_preparation_and_missing_transport(monkeypatch):
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "expected")
    monkeypatch.setenv("WHATCHIMP_API_TOKEN", "private-token")
    monkeypatch.setenv("WHATCHIMP_PHONE_NUMBER_ID", "123")
    source = browsing(batch([product(1), product(2)]))
    monkeypatch.setattr(card_route, "get_shopify_service", lambda request: SimpleNamespace(client=None))
    monkeypatch.setattr(card_route, "ProductBrowsingService", lambda client: source)
    sender = SimpleNamespace(send_card=AsyncMock())
    monkeypatch.setattr(card_route, "WhatChimpClient", lambda settings: sender)
    client = TestClient(app)
    body = {"phone_number": "923001234567", "collection_id": "111", "dry_run": True}
    result = client.post("/api/whatsapp/product-carousel", json=body, headers={"X-API-Key": "expected"})
    assert result.status_code == 200 and result.json()["submitted"] is False
    body.pop("dry_run")
    result = client.post("/api/whatsapp/product-carousel", json=body, headers={"X-API-Key": "expected"})
    assert result.status_code == 501 and result.json()["code"] == "carousel_send_unconfigured"
    sender.send_card.assert_not_awaited()


def test_safe_errors_and_no_contact_echo(monkeypatch, caplog):
    source = browsing()
    source.collection_products.side_effect = RuntimeError("private-token 923001234567")
    app.dependency_overrides[route.get_carousel_service] = lambda: ProductCarouselService(source)
    try:
        client = TestClient(app)
        result = client.post("/api/whatsapp/product-carousel", json={"phone_number": "923001234567", "collection_id": "111", "dry_run": True})
        assert result.status_code == 502
        assert "private-token" not in result.text + caplog.text
        assert "923001234567" not in result.text + caplog.text
        result = client.post("/api/whatsapp/product-carousel", json={"phone_number": "+923001234567", "collection_id": "111"})
        assert result.status_code == 422 and "923001234567" not in result.text
    finally:
        app.dependency_overrides.pop(route.get_carousel_service, None)
