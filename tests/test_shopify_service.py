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
