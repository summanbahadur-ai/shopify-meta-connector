import hmac
import logging
import os
from fastapi import APIRouter, Depends, Request
from fastapi.security import APIKeyHeader
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.dependencies import get_shopify_service
from app.clients.whatchimp_client import WhatChimpClient
from app.core.config import WhatChimpSettings, ConfigurationError, _read
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError
from app.schemas.product_browsing import BrowsingError
from app.schemas.product_card import ProductCardRequest, ProductCardResponse, ProductCardErrorResponse, CardError
from app.services.product_browsing import ProductBrowsingService
from app.services.product_card import ProductCardService

logger = logging.getLogger(__name__)


class ProductCardRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except CardError as exc:
                error = exc
            except RequestValidationError:
                error = CardError(422, "invalid_request", "Provide a digits-only international phone number, valid Shopify product ID.")
            except ConfigurationError:
                error = CardError(503, "configuration_error", "Product card sending is not configured.")
            except BrowsingError as exc:
                error = CardError(exc.status, exc.code, exc.message)
            except (ShopifyAPIError, ShopifyAuthenticationError):
                error = CardError(502, "shopify_unavailable", "The shop could not load this product.")
            except Exception:
                error = CardError(502, "product_card_failed", "The product card could not be submitted. Check send status before retrying.")
            logger.warning("Product card failure: %s", error.code)
            return JSONResponse(status_code=error.status, content={"success": False, "code": error.code, "message": error.message})
        return safe_handler


key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize_card(request: Request, key: str | None = Depends(key_header)):
    expected = _read(request.scope.get("env"), "WHATCHIMP_INBOUND_API_KEY") or os.environ.get("WHATCHIMP_INBOUND_API_KEY")
    if not expected:
        raise ConfigurationError("Missing inbound key")
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise CardError(401, "unauthorized", "A valid API key is required.")


def get_card_service(request: Request, authorized=Depends(authorize_card)):
    settings = WhatChimpSettings.from_request(request)
    browsing = ProductBrowsingService(get_shopify_service(request).client)
    return ProductCardService(browsing, WhatChimpClient(settings))


router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp product cards"], route_class=ProductCardRoute)


@router.post("/product-card", response_model=ProductCardResponse,
             responses={status: {"model": ProductCardErrorResponse}
                        for status in (401, 404, 409, 422, 429, 502, 503, 504)})
async def product_card(body: ProductCardRequest, service=Depends(get_card_service)):
    return await service.submit(body)
