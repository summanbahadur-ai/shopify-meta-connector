import pytest
from app.services.shopify_service import ShopifyService


class FakeClient:
    async def query(self, query, variables=None):
        if 'ShopConnection' in query:
            return {'shop': {'name': 'Demo Store', 'myshopifyDomain': 'demo.myshopify.com'}}
        if 'Policies' in query:
            return {'shop': {'shopPolicies': [{'id': '1', 'title': 'Refund Policy', 'type': 'REFUND_POLICY', 'body': '<p>Refunds</p>', 'url': 'https://example.com/policies/refund-policy'}]}}
        if 'Pages' in query:
            return {'pages': {'nodes': [{'id': '1', 'title': 'FAQ', 'handle': 'faq', 'body': '<p>FAQ</p>', 'bodySummary': 'FAQ', 'isPublished': True}], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        raise AssertionError('unexpected query')


@pytest.mark.asyncio
async def test_connection():
    result = await ShopifyService(FakeClient()).get_connection_status()
    assert result['connected'] is True
    assert result['shop']['name'] == 'Demo Store'


@pytest.mark.asyncio
async def test_policies_and_pages():
    service = ShopifyService(FakeClient())
    assert len(await service.get_policies()) == 1
    pages = await service.get_pages(limit=10)
    assert pages['count'] == 1


@pytest.mark.parametrize("policy_type,expected", [
    (None, ["1", "2"]), ("REFUND_POLICY", ["1"]),
    ("SHIPPING_POLICY", ["2"]), ("UNKNOWN", []), ("refund_policy", []), ("", []),
])
async def test_policy_type_filter(policy_type, expected):
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    policies = [{"id": "1", "type": "REFUND_POLICY", "body": "<p>Refunds</p>"},
                {"id": "2", "type": "SHIPPING_POLICY", "body": "<p>Shipping</p>"}]
    client = SimpleNamespace(query=AsyncMock(return_value={"shop": {"shopPolicies": policies}}))
    result = await ShopifyService(client).get_policies(policy_type)
    assert [p["id"] for p in result] == expected
    assert all("<" not in p["body"] for p in result)
    assert policies[0]["body"] == "<p>Refunds</p>" and len(policies) == 2
    client.query.assert_awaited_once()


@pytest.mark.parametrize("suffix,expected", [("", 1), ("?policy_type=REFUND_POLICY", 1),
    ("?policy_type=SHIPPING_POLICY", 0)])
def test_policy_http_filter(suffix, expected):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.dependencies import get_shopify_service
    app.dependency_overrides[get_shopify_service] = lambda: ShopifyService(FakeClient())
    try:
        response = TestClient(app).get("/api/v1/shopify/policies" + suffix)
        assert response.status_code == 200
        assert set(response.json()) == {"policies"}
        assert len(response.json()["policies"]) == expected
        if expected:
            assert response.json()["policies"][0]["body"] == "Refunds"
    finally:
        app.dependency_overrides.pop(get_shopify_service, None)
