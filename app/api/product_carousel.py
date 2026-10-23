import logging
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.product_card import get_card_service
from app.core.config import ConfigurationError
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError
from app.schemas.product_card import CardError, ProductCardErrorResponse
from app.schemas.product_browsing import BrowsingError
from app.schemas.product_carousel import ProductCarouselRequest, ProductCarouselPreview
from app.services.product_carousel import ProductCarouselService

logger = logging.getLogger(__name__)


class ProductCarouselRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except CardError as exc:
                error = exc
            except RequestValidationError:
                error = CardError(422, "invalid_request", "Provide a digits-only international phone number, valid collection ID, limit 2?10 and optional cursor/dry_run.")
            except ConfigurationError:
                error = CardError(503, "configuration_error", "WhatsApp product browsing is not configured.")
            except BrowsingError as exc:
                error = CardError(exc.status, exc.code, exc.message)
            except (ShopifyAPIError, ShopifyAuthenticationError):
                error = CardError(502, "shopify_unavailable", "The shop could not load the carousel products.")
            except Exception:
                error = CardError(502, "carousel_failed", "The product carousel could not be prepared.")
            logger.warning("Product carousel failure: %s", error.code)
            return JSONResponse(status_code=error.status, content={"success": False, "code": error.code, "message": error.message})
        return safe_handler


def get_carousel_service(card_service=Depends(get_card_service)):
    return ProductCarouselService(card_service.browsing)


router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp product carousels"], route_class=ProductCarouselRoute)


@router.post("/product-carousel", response_model=ProductCarouselPreview,
             responses={status: {"model": ProductCardErrorResponse} for status in (401, 404, 409, 422, 501, 502, 503)})
async def product_carousel(body: ProductCarouselRequest, service=Depends(get_carousel_service)):
    """Prepare 2?10 Shopify carousel cards; live sending awaits verified WhatChimp API mapping."""
    return await service.submit(body)
