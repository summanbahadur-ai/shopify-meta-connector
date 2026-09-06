from app.core.config import Settings


def test_settings_from_mapping():
    settings = Settings.from_mapping({
        'SHOPIFY_STORE_DOMAIN': 'demo.myshopify.com',
        'SHOPIFY_CLIENT_ID': 'client-id',
        'SHOPIFY_CLIENT_SECRET': 'client-secret',
        'SHOPIFY_API_VERSION': '2026-07',
    })
    assert settings.shopify_store_domain == 'demo.myshopify.com'
    assert settings.shopify_client_id == 'client-id'
    assert settings.shopify_client_secret == 'client-secret'
    assert settings.graphql_url.endswith('/admin/api/2026-07/graphql.json')
    assert settings.token_url.endswith('/admin/oauth/access_token')
