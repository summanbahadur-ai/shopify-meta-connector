from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader

from app.api.dependencies import get_shopify_service
from app.core.config import ConfigurationError, _read
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError
from app.schemas.product_browsing import BrowsingError, BrowsingErrorResponse, CollectionOptions, ProductOptions, ProductDetails
from app.services.product_browsing import ProductBrowsingService

logger = logging.getLogger(__name__)


class ProductBrowsingRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                if request.path_params.get("product_id") == "":
                    raise BrowsingError(404, "not_found", "This endpoint is not available.")
                return await handler(request)
            except BrowsingError as exc:
                error = exc
            except RequestValidationError:
                error = BrowsingError(422, "invalid_request", "Check the ID, limit (1–50), and pagination cursor.")
            except ConfigurationError:
                error = BrowsingError(503, "configuration_error", "Product browsing is not configured. Please contact support.")
            except (ShopifyAuthenticationError, ShopifyAPIError):
                error = BrowsingError(502, "shopify_unavailable", "The shop could not load this selection. Please try again or contact support.")
            except HTTPException as exc:
                error = BrowsingError(exc.status_code, "invalid_request", "This request could not be completed.")
            except Exception:
                error = BrowsingError(500, "internal_error", "This selection could not be loaded. Please try again.")
            # Log category only: no tokens, query inputs, descriptions, or raw errors.
            if error.status >= 500:
                logger.warning("Product browsing failure: %s", error.code)
            return JSONResponse(status_code=error.status, content=BrowsingErrorResponse(code=error.code, message=error.message).model_dump())

        return safe_handler


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_browsing_key(request: Request, key: str | None = Depends(api_key_header)) -> None:
    expected = _read(request.scope.get("env"), "PRODUCT_BROWSING_API_KEY") or os.environ.get("PRODUCT_BROWSING_API_KEY")
    if not expected:
        raise ConfigurationError("Product browsing key is missing")
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise BrowsingError(401, "unauthorized", "A valid API key is required.")


def get_product_browsing_service(request: Request, authorized: None = Depends(require_browsing_key)) -> ProductBrowsingService:
    return ProductBrowsingService(get_shopify_service(request).client)


router = APIRouter(prefix="/products", tags=["Product browsing"], route_class=ProductBrowsingRoute,
                   responses={s: {"model": BrowsingErrorResponse} for s in (401, 404, 422, 500, 502, 503)})


@router.get("/collections", response_model=CollectionOptions)
async def menu_collections(service: ProductBrowsingService = Depends(get_product_browsing_service)):
    """Collections linked by the configured navigation menu, in menu order."""
    return await service.collection_options()


@router.get("/collection-products", response_model=ProductOptions)
async def collection_products_query(collection_id: str = Query(..., max_length=100),
                                    service: ProductBrowsingService = Depends(get_product_browsing_service)):
    """Query-parameter alias for slash-containing Shopify collection GIDs."""
    return await service.product_options(collection_id)


@router.get("/details", response_model=ProductDetails)
async def product_details_query(product_id: str = Query(..., max_length=100), collection_id: str | None = Query(None, max_length=100),
                                service: ProductBrowsingService = Depends(get_product_browsing_service)):
    """Query-parameter alias for product GIDs; optional collection context."""
    return await service.product_details(product_id, collection_id)


@router.get("/collections/{collection_id:path}/products", response_model=ProductOptions)
async def collection_products(collection_id: str,
                              service: ProductBrowsingService = Depends(get_product_browsing_service)):
    """Visible products belonging to an allowed collection. Numeric IDs are convenient in paths."""
    return await service.product_options(collection_id)


@router.get("/{product_id:path}", response_model=ProductDetails)
async def product_details(product_id: str, collection_id: str | None = Query(None, max_length=100),
                          service: ProductBrowsingService = Depends(get_product_browsing_service)):
    """Visible product details and deterministic WhatsApp message, restricted to the menu."""
    return await service.product_details(product_id, collection_id)
