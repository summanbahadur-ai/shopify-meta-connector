from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

C = "gid://shopify/Collection/1"
P = "gid://shopify/Product/2"


def menu(items=None):
    return {"menu": {"id": "gid://shopify/Menu/235088314461", "title": "Shop", "items": items or []}}


def link(id=C, title="Menu label", tags=None, **kwargs):
    return dict(id="item", type="COLLECTION", resourceId=id, title=title, url="/collections/test", tags=tags or [], **kwargs)


def product(**changes):
    data = dict(id=P, title="Cleanser 🌿", handle="cleanser", status="ACTIVE", tags=["Face"],
                onlineStoreUrl="https://doctorselements.com/products/cleanser", description="Gentle & clean",
                descriptionHtml="<p>Gentle &amp; clean</p>", vendor="Dr Elements", productType="Cleanser",
                featuredMedia=None, priceRangeV2={"minVariantPrice": {"amount": "10.00", "currencyCode": "USD"},
                                                 "maxVariantPrice": {"amount": "10.00", "currencyCode": "USD"}},
                variants={"nodes": [{"id": "gid://shopify/ProductVariant/3", "title": "250ML", "price": "10.00",
                                      "compareAtPrice": "15.00", "availableForSale": True,
                                      "selectedOptions": [{"name": "Size", "value": "250ML"}]}],
                          "pageInfo": {"hasNextPage": False, "endCursor": None}})
    data.update(changes)
    return data


def page(products, more=False, cursor="next"):
    return {"collection": {"id": C, "title": "Shopify title", "products": {
        "edges": [{"cursor": f"c{i}", "node": p} for i, p in enumerate(products)],
        "pageInfo": {"hasNextPage": more, "endCursor": cursor if more else None}}}}


def service(*responses):
    from app.services.product_browsing import ProductBrowsingService
    client = type("Client", (), {})()
    client.query_with_retry = AsyncMock(side_effect=list(responses))
    return ProductBrowsingService(client)


async def test_menu_order_nesting_duplicates_and_labels():
    s = service(menu([link(), {"type": "PAGE", "items": [link("gid://shopify/Collection/4", "Second")]},
                      link(title="Duplicate"), {"type": "PRODUCT", "resourceId": P}, link("bad")]))
    result = await s.collections()
    assert [x.title for x in result.collections] == ["Menu label", "Second"]
    assert [x.id for x in result.collections] == [C, "gid://shopify/Collection/4"]
    assert result.total == 2


async def test_empty_menu():
    assert (await service(menu()).collections()).collections == []


async def test_missing_menu():
    with pytest.raises(Exception) as exc:
        await service({"menu": None}).collections()
    assert exc.value.code == "menu_unavailable"


async def test_tags_preserved_and_applied():
    s = service(menu([link(tags=["Face"])]), page([product(tags=["Hair"]), product()]))
    result = await s.collection_products(C, 10)
    assert len(result.products) == 1
    assert result.collection_title == "Menu label"


async def test_collection_denied_before_fetch():
    s = service(menu())
    with pytest.raises(Exception) as exc:
        await s.collection_products(C)
    assert exc.value.status == 404
    assert s.client.query_with_retry.await_count == 1


@pytest.mark.parametrize("changes", [{"status": "DRAFT"}, {"status": "ARCHIVED"}, {"status": "UNLISTED"}, {"onlineStoreUrl": None}])
async def test_invisible_products_omitted(changes):
    assert not (await service(menu([link()]), page([product(**changes)])).collection_products(C)).products


async def test_product_prices_images_and_discount():
    result = (await service(menu([link()]), page([product()])).collection_products(C)).products[0]
    assert result.price == "10.00"
    assert result.currency == "USD"
    assert result.description == "Gentle & clean"
    assert result.compare_at_price == "15.00"
    assert result.on_sale is True
    assert result.image_url is None


async def test_single_price_and_compare_price_use_same_available_variant():
    p = product()
    p["priceRangeV2"]["maxVariantPrice"]["amount"] = "20.00"
    p["variants"]["nodes"].append(dict(p["variants"]["nodes"][0], price="20.00", compareAtPrice="25.00"))
    result = (await service(menu([link()]), page([p])).collection_products(C)).products[0]
    assert result.price == "10.00"
    assert result.compare_at_price == "15.00"


async def test_fill_visible_page_and_cursor():
    s = service(menu([link()]), page([product(status="DRAFT")], True, "hidden"), page([product()], True, "visible"))
    r = await s.collection_products(C, 1)
    assert len(r.products) == 1 and r.pagination.next_cursor == "visible"
    assert s.client.query_with_retry.call_args_list[2].args[1]["after"] == "hidden"


async def test_empty_collection():
    assert (await service(menu([link()]), page([])).collection_products(C)).products == []


@pytest.mark.parametrize("bad", ["bad", "gid://shopify/Product/1", "0", "-1"])
async def test_invalid_collection_id(bad):
    with pytest.raises(Exception) as exc:
        await service().collection_products(bad)
    assert exc.value.status == 422


async def test_details_context_and_whatsapp():
    s = service(menu([link()]), {"product": product()}, {"product": {"inCollection": True}})
    r = await s.product_details(P, C)
    assert r.variants[0].available and r.description == "Gentle & clean"
    assert "USD 10" in r.whatsapp_message and "250ML" in r.whatsapp_message
    assert r.product_url in r.whatsapp_message


async def test_details_without_context_checks_allowed_membership():
    s = service(menu([link()]), {"product": product()}, {"product": {"collections": {
        "nodes": [{"id": C}], "pageInfo": {"hasNextPage": False}}}})
    assert (await s.product_details(P)).id == P


@pytest.mark.parametrize("p", [None, product(status="DRAFT"), product(onlineStoreUrl=None)])
async def test_details_missing_or_invisible(p):
    with pytest.raises(Exception) as exc:
        await service(menu([link()]), {"product": p}).product_details(P)
    assert exc.value.status == 404


async def test_details_outside_menu():
    with pytest.raises(Exception) as exc:
        await service(menu([link()]), {"product": product()}, {"product": {"inCollection": False}}).product_details(P, C)
    assert exc.value.status == 404


async def test_html_sanitized_and_unavailable_variants_not_advertised():
    p = product(description="", descriptionHtml="<script>secret()</script><style>bad</style><p>Safe &amp; 🌿</p>")
    p["variants"]["nodes"][0]["availableForSale"] = False
    r = await service(menu([link()]), {"product": p}, {"product": {"inCollection": True}}).product_details(P, C)
    assert r.description == "Safe & 🌿"
    assert "250ML" not in r.whatsapp_message and "Out of stock" in r.whatsapp_message
    assert "secret" not in r.whatsapp_message


@pytest.mark.parametrize("description", ["", "word " * 1000])
async def test_description_empty_and_long(description):
    p = product(description=description, descriptionHtml="")
    r = await service(menu([link()]), {"product": p}, {"product": {"inCollection": True}}).product_details(P, C)
    assert description.strip() in r.whatsapp_message
    assert r.description == description.strip()


async def test_variants_paginate():
    p = product()
    p["variants"]["pageInfo"] = {"hasNextPage": True, "endCursor": "v1"}
    extra = deepcopy(p["variants"]["nodes"][0]); extra["title"] = "500ML"
    s = service(menu([link()]), {"product": p}, {"product": {"variants": {
        "nodes": [extra], "pageInfo": {"hasNextPage": False}}}}, {"product": {"inCollection": True}})
    assert len((await s.product_details(P, C)).variants) == 2


async def test_collection_query_cost_bounded():
    s = service(menu([link()]), page([]))
    await s.collection_products(C, 50)
    assert s.client.query_with_retry.call_args.args[1]["first"] <= 10


@pytest.mark.parametrize("error", ["permission", "graphql", "timeout"])
def test_safe_upstream_errors(monkeypatch, error):
    from app.api.product_browsing import get_product_browsing_service
    from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError
    s = service()
    kind = ShopifyAuthenticationError if error == "permission" else ShopifyAPIError
    s.client.query_with_retry.side_effect = kind("PRIVATE TOKEN AND SHOPIFY ERROR")
    app.dependency_overrides[get_product_browsing_service] = lambda: s
    try:
        response = TestClient(app).get("/api/v1/shopify/products/collections")
        assert response.status_code == 502
        assert "PRIVATE" not in response.text
        assert response.json()["code"] == "shopify_unavailable"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("url", [
    "/products/collection-products?collection_id=bad", "/products/bad",
    "/products/collections/1/products?limit=51", "/products/collections/1/products?limit=0",
    "/products/collection-products", "/products/details?product_id=2&collection_id=bad",
])
def test_route_validation(url):
    from app.api.product_browsing import get_product_browsing_service
    app.dependency_overrides[get_product_browsing_service] = lambda: service()
    try:
        response = TestClient(app).get("/api/v1/shopify" + url)
        assert response.status_code == 422
        assert response.json()["success"] is False
    finally:
        app.dependency_overrides.clear()


def test_collection_route_response_schema():
    from app.api.product_browsing import get_product_browsing_service
    app.dependency_overrides[get_product_browsing_service] = lambda: service(menu([link(tags=["Face"])]))
    try:
        r = TestClient(app).get("/api/v1/shopify/products/collections")
        assert r.status_code == 200
        assert r.json()["collections"][0] == {"id": C, "title": "Menu label", "url": "/collections/test", "tags": ["Face"]}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("query_alias", [True, False])
def test_product_routes_accept_gids(query_alias):
    from app.api.product_browsing import get_product_browsing_service
    s = service(menu([link()]), {"product": product()}, {"product": {"inCollection": True}})
    app.dependency_overrides[get_product_browsing_service] = lambda: s
    try:
        path = "/details" if query_alias else f"/{P}"
        params = {"collection_id": C}
        if query_alias:
            params["product_id"] = P
        r = TestClient(app).get("/api/v1/shopify/products" + path, params=params)
        assert r.status_code == 200
        assert r.json()["id"] == P and r.json()["whatsapp_message"]
    finally:
        app.dependency_overrides.clear()


def test_auth_missing_configuration(monkeypatch):
    monkeypatch.delenv("PRODUCT_BROWSING_API_KEY", raising=False)
    assert TestClient(app).get("/api/v1/shopify/products/collections").status_code == 503


def test_auth_valid_key_reaches_service(monkeypatch):
    from app.api import product_browsing
    from types import SimpleNamespace
    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "test-key")
    client = SimpleNamespace(query_with_retry=AsyncMock(return_value=menu()))
    monkeypatch.setattr(product_browsing, "get_shopify_service", lambda request: SimpleNamespace(client=client))
    r = TestClient(app).get("/api/v1/shopify/products/collections", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200 and r.json()["total"] == 0


async def test_three_decimal_currency_preserved_in_message():
    p = product()
    for key in ("minVariantPrice", "maxVariantPrice"):
        p["priceRangeV2"][key] = {"amount": "1.234", "currencyCode": "BHD"}
    p["variants"]["nodes"][0].update(price="1.234", compareAtPrice="2.345")
    r = await service(menu([link()]), {"product": p}, {"product": {"inCollection": True}}).product_details(P, C)
    assert "BHD 1.234" in r.whatsapp_message and "BHD 2.345" in r.whatsapp_message


def test_summary_query_avoids_nested_variant_options():
    from app.clients.product_queries import COLLECTION_PRODUCTS_QUERY
    assert "selectedOptions" not in COLLECTION_PRODUCTS_QUERY
    assert "availableForSale" in COLLECTION_PRODUCTS_QUERY


async def test_duplicate_first_tags_and_label_win():
    s = service(menu([link(title="First", tags=["Face"]), link(title="Second")]))
    r = await s.collections()
    assert r.collections[0].tags == ["Face"] and r.collections[0].title == "First"


@pytest.mark.parametrize("context", [C, None])
async def test_details_tag_mismatch_denied(context):
    s = service(menu([link(tags=["Not present"])]), {"product": product()})
    with pytest.raises(Exception) as exc:
        await s.product_details(P, context)
    assert exc.value.status == 404


async def test_membership_follows_pagination():
    s = service(menu([link()]), {"product": product()},
        {"product": {"collections": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "m1"}}}},
        {"product": {"collections": {"nodes": [{"id": C}], "pageInfo": {"hasNextPage": False}}}})
    assert (await s.product_details(P)).id == P
    assert s.client.query_with_retry.call_args.args[1]["after"] == "m1"


async def test_variant_budget_is_explicit_error(monkeypatch):
    monkeypatch.setattr("app.services.product_browsing.MAX_VARIANT_PAGES", 1)
    p = product(); p["variants"]["pageInfo"] = {"hasNextPage": True, "endCursor": "v1"}
    with pytest.raises(Exception) as exc:
        await service(menu([link()]), {"product": p}).product_details(P, C)
    assert exc.value.code == "lookup_limit"


async def test_membership_budget_fails_closed(monkeypatch):
    monkeypatch.setattr("app.services.product_browsing.MAX_MEMBERSHIP_PAGES", 1)
    s = service(menu([link()]), {"product": product()},
        {"product": {"collections": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "m1"}}}})
    with pytest.raises(Exception) as exc:
        await s.product_details(P)
    assert exc.value.code == "lookup_limit"


async def test_collection_budget_returns_resumable_empty_page(monkeypatch):
    monkeypatch.setattr("app.services.product_browsing.MAX_COLLECTION_PAGES", 1)
    r = await service(menu([link()]), page([product(status="DRAFT")], True, "resume")).collection_products(C)
    assert not r.products and r.pagination.next_cursor == "resume"


async def test_nonadvancing_cursor_is_error():
    with pytest.raises(Exception) as exc:
        await service(menu([link()]), page([], True, "same")).collection_products(C, cursor="same")
    assert exc.value.code == "invalid_upstream_response"


async def test_selected_variant_discount_does_not_require_all_variants():
    p = product(); p["variants"]["pageInfo"] = {"hasNextPage": True, "endCursor": "v1"}
    r = await service(menu([link()]), page([p])).collection_products(C)
    assert r.products[0].compare_at_price == "15.00" and r.products[0].on_sale


async def test_currency_mismatch_rejected():
    p = product(); p["priceRangeV2"]["maxVariantPrice"]["currencyCode"] = "EUR"
    with pytest.raises(Exception) as exc:
        await service(menu([link()]), page([p])).collection_products(C)
    assert exc.value.status == 502


@pytest.mark.parametrize("url", ["/collections", "/collection-products?collection_id=1", "/collections/1/products", "/details?product_id=2", "/2"])
def test_wrong_key_on_all_browsing_routes(monkeypatch, url):
    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "test-key")
    r = TestClient(app).get("/api/v1/shopify/products" + url, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_worker_key_takes_precedence(monkeypatch):
    from app.api.product_browsing import require_browsing_key
    from starlette.requests import Request
    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "local")
    request = Request({"type": "http", "env": {"PRODUCT_BROWSING_API_KEY": "worker"}})
    require_browsing_key(request, "worker")
    with pytest.raises(Exception) as exc:
        require_browsing_key(request, "local")
    assert exc.value.status == 401


@pytest.mark.parametrize("query_alias", [True, False])
def test_collection_routes_accept_gids(query_alias):
    from app.api.product_browsing import get_product_browsing_service
    app.dependency_overrides[get_product_browsing_service] = lambda: service(menu([link()]), page([product()]))
    try:
        path = "/collection-products" if query_alias else f"/collections/{C}/products"
        params = {"collection_id": C} if query_alias else {}
        r = TestClient(app).get("/api/v1/shopify/products" + path, params=params)
        assert r.status_code == 200 and r.json()["collection_id"] == C
        assert r.json()["products"][0]["price"] == "10.00"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("url", ["/collections/1/products", "/2?collection_id=1"])
def test_route_menu_rejection_is_404(url):
    from app.api.product_browsing import get_product_browsing_service
    app.dependency_overrides[get_product_browsing_service] = lambda: service(menu())
    try:
        r = TestClient(app).get("/api/v1/shopify/products" + url)
        assert r.status_code == 404 and r.json()["code"] == "not_found"
    finally:
        app.dependency_overrides.clear()


async def test_shopify_cdn_image_mapped():
    p = product(featuredMedia={"image": {"url": "https://cdn.shopify.com/s/files/image.jpg", "altText": "Cleanser"}})
    r = await service(menu([link()]), page([p])).collection_products(C)
    assert r.products[0].image_url == "https://cdn.shopify.com/s/files/image.jpg"
    assert r.products[0].image_alt == "Cleanser"


def test_documented_graphql_matches_actual_queries():
    from pathlib import Path
    from app.clients import product_queries as q
    text = (Path(__file__).resolve().parents[1] / "docs/services/product.md").read_text(encoding="utf-8")
    for name in ("MENU_QUERY", "COLLECTION_PRODUCTS_QUERY", "PRODUCT_DETAILS_QUERY", "VARIANTS_QUERY", "MEMBERSHIP_QUERY", "PRODUCT_COLLECTIONS_QUERY"):
        assert getattr(q, name).strip() in text


def test_new_routes_require_authentication(monkeypatch):
    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "test-key")
    response = TestClient(app).get("/api/v1/shopify/products/collections")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_openapi_documents_browsing():
    paths = app.openapi()["paths"]
    assert "/api/v1/shopify/products/collections" in paths
    assert "/api/v1/shopify/products/{product_id}" in paths


def test_unrestricted_list_endpoint_removed():
    assert "/api/v1/shopify/products" not in app.openapi()["paths"]
    assert TestClient(app).get("/api/v1/shopify/products").status_code == 404


async def test_price_uses_first_available_not_sold_out_variant():
    p = product()
    p["variants"]["nodes"][0]["availableForSale"] = False
    p["variants"]["nodes"].append(dict(p["variants"]["nodes"][0], price="20.00", compareAtPrice="25.00", availableForSale=True))
    r = await service(menu([link()]), page([p])).collection_products(C)
    assert r.products[0].price == "20.00" and r.products[0].compare_at_price == "25.00"


async def test_collection_full_description_is_not_truncated():
    text = "Full product details " * 100
    p = product(descriptionHtml=f"<p>{text}</p>")
    r = await service(menu([link()]), page([p])).collection_products(C)
    assert r.products[0].description == text.strip()


async def test_available_variant_beyond_first_page_used_for_listing():
    p = product()
    p["variants"]["nodes"][0]["availableForSale"] = False
    p["variants"]["pageInfo"] = {"hasNextPage": True, "endCursor": "v1"}
    v = dict(p["variants"]["nodes"][0], availableForSale=True, price="12.50", compareAtPrice="15.50")
    s = service(menu([link()]), page([p]), {"product": {"variants": {"nodes": [v], "pageInfo": {"hasNextPage": False}}}})
    assert (await s.collection_products(C)).products[0].price == "12.50"


async def test_all_sold_out_uses_first_variant_price():
    p = product()
    p["variants"]["nodes"][0]["availableForSale"] = False
    r = await service(menu([link()]), page([p])).collection_products(C)
    assert r.products[0].price == "10.00"


async def test_confirmed_pkr_uses_rupee_label_in_message():
    p = product()
    for key in ("minVariantPrice", "maxVariantPrice"):
        p["priceRangeV2"][key]["currencyCode"] = "PKR"
    r = await service(menu([link()]), {"product": p}, {"product": {"inCollection": True}}).product_details(P, C)
    assert r.currency == "PKR" and "Price: Rs. 10" in r.whatsapp_message
