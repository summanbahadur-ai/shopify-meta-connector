from fastapi import Request

from app.clients.shopify_client import ShopifyClient
from app.core.config import Settings
from app.services.shopify_service import ShopifyService


def get_shopify_service(request: Request) -> ShopifyService:
    settings = Settings.from_request(request)
    return ShopifyService(ShopifyClient(settings))
