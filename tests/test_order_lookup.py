from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api.v1.shopify import get_order_status_service
from app.main import app
from app.services.shopify_service import ShopifyService


def connection(nodes, more=False, cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


def candidate(name="#1001", identifier="1"):
    return {"id": f"gid://shopify/Order/{identifier}", "name": name}


def item(identifier="a", title="Blue Shirt", quantity=1, shipping=True):
    return {"id": identifier, "title": title, "quantity": quantity,
            "currentQuantity": quantity, "requiresShipping": shipping}


def fulfillment(items, display="IN_TRANSIT", identifier="f1", **overrides):
    result = {
        "id": identifier, "status": "SUCCESS", "displayStatus": display,
        "requiresShipping": True, "deliveredAt": None, "inTransitAt": None,
        "trackingInfo": [{"company": "Example Carrier", "number": "TRACK123",
                          "url": "https://example.com/track/TRACK123"}],
        "fulfillmentLineItems": connection([
            {"quantity": x["quantity"], "lineItem": {"id": x["id"], "title": x["title"]}}
            for x in items
        ]),
    }
    result.update(overrides)
    return result


def details(items=None, fulfillments=None, **overrides):
    result = {
        **candidate(), "cancelledAt": None, "displayFinancialStatus": "PAID",
        "displayFulfillmentStatus": "UNFULFILLED",
        "lineItems": connection(items if items is not None else [item()]),
        "fulfillments": fulfillments or [],
    }
    result.update(overrides)
    return result


class GraphQLScript:
    """Replace only external Shopify calls; run real routes/services/formatting."""

    def __init__(self, steps=()):
        self.steps = list(steps)
        self.calls = []

    async def query(self, document, variables=None):
        self.calls.append((document, variables))
        assert self.steps, "Unexpected upstream call"
        operation, expected_variables, response = self.steps.pop(0)
        assert f"query {operation}(" in document
        assert variables == expected_variables
        return deepcopy(response)


def lookup_script(order=None, search='name:"#1001"'):
    return GraphQLScript([
        ("OrderLookup", {"first": 50, "after": None, "query": search},
         {"orders": connection([candidate()])}),
        ("OrderStatusDetails", {"id": "gid://shopify/Order/1"},
         {"order": order or details()}),
    ])


@pytest.fixture
def api():
    script = GraphQLScript()
    app.dependency_overrides[get_order_status_service] = lambda: ShopifyService(script)
    with TestClient(app) as client:
        yield client, script
    app.dependency_overrides.clear()


def test_order_listing_is_not_public(api):
    client, script = api
    assert client.get("/api/v1/shopify/orders").status_code == 404
    assert "/api/v1/shopify/orders" not in client.get("/openapi.json").json()["paths"]
    assert not script.calls


@pytest.mark.parametrize("params", [
    {}, {"email": ""}, {"phone": "  "}, {"order_number": " "},
    {"email": "bad-email"}, {"phone": "4155552671"}, {"phone": "+10000000000"},
    {"email": "buyer@example.com", "phone": "123"},
    {"order_number": "1001\nOR email:*"}, {"order_number": "x" * 129},
])
def test_invalid_lookup_never_calls_shopify(api, params):
    client, script = api
    response = client.get("/api/v1/shopify/orders/status", params=params)
    assert response.status_code == 422
    assert not script.calls


def test_route_returns_formatted_order_without_customer_data(api):
    client, script = api
    script.steps = lookup_script().steps
    response = client.get("/api/v1/shopify/orders/status", params={"order_number": " 1001 "})
    assert response.status_code == 200
    body = response.json()
    assert body["order_number"] == "#1001"
    assert body["status"] == "processing"
    assert "being processed" in body["message"]
    assert body["items"] == [{"title": "Blue Shirt", "quantity": 1}]
    assert "buyer@example.com" not in response.text
    assert "+14155552671" not in response.text
    assert not script.steps


@pytest.mark.asyncio
async def test_order_number_lookup_requires_exact_match():
    script = GraphQLScript([
        ("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
         {"orders": connection([candidate(name="#10010", identifier="2"), candidate()])}),
        ("OrderStatusDetails", {"id": "gid://shopify/Order/1"}, {"order": details()}),
    ])
    result = await ShopifyService(script).get_order_status(order_number=" 1001 ")
    assert result["order_number"] == "#1001"


@pytest.mark.asyncio
async def test_missing_order_number_is_invalid_for_direct_service():
    from pydantic import ValidationError
    from app.schemas.order_status import OrderLookup

    with pytest.raises(ValidationError):
        OrderLookup()


def test_openapi_requires_only_order_number(api):
    client, _ = api
    params = client.get("/openapi.json").json()["paths"]["/api/v1/shopify/orders/status"]["get"]["parameters"]
    assert [(p["name"], p["required"]) for p in params] == [("order_number", True)]


def test_duplicate_order_names_on_later_page_are_not_guessed(api):
    client, script = api
    script.steps = [
        ("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
         {"orders": connection([candidate()], True, "next")}),
        ("OrderLookup", {"first": 50, "after": "next", "query": 'name:"#1001"'},
         {"orders": connection([candidate(identifier="2")])}),
    ]
    response = client.get("/api/v1/shopify/orders/status", params={"order_number": "1001"})
    assert response.status_code == 409
    assert "order number" in response.json()["detail"].lower()
    assert "#1001" not in response.text


def test_no_matches_is_404(api):
    client, script = api
    script.steps = [("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
                     {"orders": connection([])})]
    assert client.get("/api/v1/shopify/orders/status", params={"order_number": "1001"}).status_code == 404


@pytest.mark.asyncio
async def test_search_value_is_escaped_not_interpreted_as_operator():
    name = 'WEB-1001" OR name:*'
    script = GraphQLScript([
        ("OrderLookup", {"first": 50, "after": None, "query": 'name:"WEB-1001\\" OR name\\:*"'},
         {"orders": connection([])}),
    ])
    assert await ShopifyService(script).get_order_status(order_number=name) is None


@pytest.mark.asyncio
async def test_order_and_fulfillment_item_pagination():
    a, b = item(), item("b", "Black Cap")
    shipped = fulfillment([a])
    shipped["fulfillmentLineItems"] = connection(shipped["fulfillmentLineItems"]["nodes"], True, "fnext")
    order = details([a], [shipped], displayFulfillmentStatus="FULFILLED")
    order["lineItems"] = connection([a], True, "inext")
    script = lookup_script(order)
    script.steps.extend([
        ("OrderItems", {"id": "gid://shopify/Order/1", "after": "inext"},
         {"order": {"lineItems": connection([b])}}),
        ("FulfillmentItems", {"id": "f1", "after": "fnext"},
         {"fulfillment": {"fulfillmentLineItems": connection([
             {"quantity": 1, "lineItem": {"id": "b", "title": "Black Cap"}},
         ])}}),
    ])
    result = await ShopifyService(script).get_order_status("1001")
    assert result["status"] == "shipped"
    assert "Blue Shirt" in result["message"] and "Black Cap" in result["message"]
    assert len(result["shipments"][0]["items"]) == 2
    assert not script.steps


@pytest.mark.asyncio
@pytest.mark.parametrize("order,status,phrase", [
    (details(), "processing", "being processed"),
    (details(displayFinancialStatus="PENDING"), "awaiting_payment", "awaiting payment"),
    (details(displayFinancialStatus="PARTIALLY_PAID"), "awaiting_payment", "awaiting payment"),
    (details(cancelledAt="2026-10-01T12:00:00Z"), "cancelled", "cancelled"),
    (details(displayFulfillmentStatus="FULFILLED"), "fulfilled", "fulfilled"),
    (details(displayFulfillmentStatus="ON_HOLD"), "on_hold", "on hold"),
    (details(fulfillments=[fulfillment([item()], "IN_TRANSIT")]), "shipped", "has shipped"),
    (details(fulfillments=[fulfillment([item()], "OUT_FOR_DELIVERY")]), "out_for_delivery", "out for delivery"),
    (details(fulfillments=[fulfillment([item()], "DELIVERED")]), "delivered", "delivered"),
    (details(fulfillments=[fulfillment([item()], "FAILURE")]), "delivery_exception", "delivery issue"),
    (details(fulfillments=[fulfillment([item()], "CONFIRMED")]), "processing", "being processed"),
    (details(fulfillments=[fulfillment([item()], "IN_TRANSIT", status="CANCELLED")]), "processing", "being processed"),
])
async def test_status_uses_actual_evidence(order, status, phrase):
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == status
    assert phrase in result["message"]


@pytest.mark.asyncio
async def test_split_shipments_preserve_items_tracking_and_remaining_quantity():
    a, b = item(quantity=2), item("b", "Black Cap")
    f1 = fulfillment([item()], "DELIVERED")
    f2 = fulfillment([b], "IN_TRANSIT", identifier="f2", trackingInfo=[])
    result = await ShopifyService(lookup_script(details([a, b], [f1, f2]))).get_order_status("1001")
    assert result["status"] == "partially_shipped"
    assert result["remaining_items"] == [{"title": "Blue Shirt", "quantity": 1}]
    assert "1 Blue Shirt" in result["message"]
    assert "TRACK123" in result["message"]
    assert "not yet available" in result["message"]
    assert result["shipments"][0]["items"] == [{"title": "Blue Shirt", "quantity": 1}]
    assert result["shipments"][1]["tracking"] == []


@pytest.mark.asyncio
async def test_digital_fulfillment_does_not_claim_shipped():
    digital = item(shipping=False)
    order = details([digital], [fulfillment([digital], "DELIVERED", requiresShipping=False)],
                    displayFulfillmentStatus="FULFILLED")
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == "fulfilled"
    assert "shipped" not in result["message"]


def test_broken_pagination_is_not_reported_as_unique(api):
    client, script = api
    script.steps = [("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
                     {"orders": connection([candidate()], True, None)})]
    assert client.get("/api/v1/shopify/orders/status", params={"order_number": "1001"}).status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("display,status", [
    ("CARRIER_PICKED_UP", "shipped"), ("DELAYED", "delivery_exception"),
    ("NOT_DELIVERED", "delivery_exception"),
])
async def test_carrier_and_delivery_exception_states(display, status):
    order = details(fulfillments=[fulfillment([item()], display)])
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == status


@pytest.mark.asyncio
async def test_mixed_digital_and_physical_order_does_not_claim_digital_item_shipped():
    physical, digital = item(), item("ebook", "Digital Book", shipping=False)
    order = details([physical, digital], [fulfillment([physical])])
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == "shipped"
    assert "Digital Book" not in result["message"].splitlines()[0]
    assert result["items"][1]["title"] == "Digital Book"


@pytest.mark.parametrize("params", [{}, {"email": "bad"}, {"order_number": " "}])
def test_invalid_lookup_is_validated_before_settings_dependency(monkeypatch, params):
    def unconfigured_service(request):
        raise AssertionError("Settings should not be loaded for invalid lookup")

    monkeypatch.setattr("app.api.v1.shopify.get_shopify_service", unconfigured_service)
    with TestClient(app) as client:
        response = client.get("/api/v1/shopify/orders/status", params=params)
        assert response.status_code == 422


def test_lookup_budget_returns_503_without_false_success(api, monkeypatch):
    from app.services.order_lookup import OrderLookupService

    client, script = api
    monkeypatch.setattr(OrderLookupService, "MAX_REQUESTS", 1)
    script.steps = [("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
                     {"orders": connection([candidate()])})]
    response = client.get("/api/v1/shopify/orders/status", params={"order_number": "1001"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_message_copy_can_be_extended_without_changing_lookup(monkeypatch):
    from app.messaging.order_messages import ORDER_MESSAGES

    monkeypatch.setitem(ORDER_MESSAGES, "processing", "Order {order_number}: preparing your items.")
    result = await ShopifyService(lookup_script()).get_order_status("1001")
    assert result["message"].startswith("Order #1001: preparing your items.")


@pytest.mark.asyncio
async def test_order_search_paginates_and_deduplicates_matches():
    script = GraphQLScript([
        ("OrderLookup", {"first": 50, "after": None, "query": 'name:"#1001"'},
         {"orders": connection([], True, "onext")}),
        ("OrderLookup", {"first": 50, "after": "onext", "query": 'name:"#1001"'},
         {"orders": connection([candidate(), candidate()])}),
        ("OrderStatusDetails", {"id": "gid://shopify/Order/1"}, {"order": details()}),
    ])
    assert (await ShopifyService(script).get_order_status("1001"))["order_number"] == "#1001"


@pytest.mark.asyncio
async def test_tracking_url_is_not_executable():
    order = details(fulfillments=[fulfillment([item()], trackingInfo=[
        {"company": None, "number": None, "url": "javascript:alert(1)"}])])
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["shipments"][0]["tracking"][0]["url"] is None
    assert "javascript:" not in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("display", ["FULFILLED", "MARKED_AS_FULFILLED"])
async def test_explicit_fulfillment_is_not_described_as_preparing(display):
    order = details(fulfillments=[fulfillment([item()], display)], displayFulfillmentStatus="FULFILLED")
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == "fulfilled"
    assert result["shipments"][0]["status"] == "fulfilled"
    assert "being prepared" not in result["message"]


@pytest.mark.asyncio
async def test_delayed_shipment_overrides_past_transit_evidence():
    order = details(fulfillments=[fulfillment([item()], "DELAYED", inTransitAt="2026-10-01T12:00:00Z")])
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["status"] == "delivery_exception"


@pytest.mark.asyncio
async def test_mixed_order_delivery_message_explicitly_scopes_physical_items():
    physical, digital = item(), item("ebook", "Digital Book", shipping=False)
    order = details([physical, digital], [fulfillment([physical], "DELIVERED")])
    result = await ShopifyService(lookup_script(order)).get_order_status("1001")
    assert result["message"].startswith("The physical items in your order #1001")
