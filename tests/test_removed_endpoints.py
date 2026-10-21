import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize('path', ['/shop', '/pages'])
def test_removed_endpoints_are_not_exposed(path):
    client = TestClient(app)
    url = '/api/v1/shopify' + path
    assert url not in client.get('/openapi.json').json()['paths']
    assert client.get(url).status_code == 404


def test_csv_export_is_rejected_as_an_invalid_product_id(monkeypatch):
    from types import SimpleNamespace
    from app.api import product_browsing

    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "test-key")
    # No Shopify calls are needed to reject this invalid ID.
    monkeypatch.setattr(product_browsing, "get_shopify_service", lambda request: SimpleNamespace(client=None))
    client = TestClient(app)
    url = "/api/v1/shopify/products/export.csv"
    assert url not in client.get("/openapi.json").json()["paths"]
    response = client.get(url, headers={"X-API-Key": "test-key"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_id"

