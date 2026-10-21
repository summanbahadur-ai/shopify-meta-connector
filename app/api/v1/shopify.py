from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.dependencies import get_shopify_service
from app.api.order_errors import OrderStatusRoute
from app.api.product_browsing import router as product_browsing_router
from app.services.shopify_service import ShopifyService
from app.schemas.order_status import OrderLookup, OrderLookupErrorResponse, OrderStatusResponse

router = APIRouter(prefix="/shopify", tags=["Shopify"])
order_router = APIRouter(route_class=OrderStatusRoute)


@router.get("/connection")
async def connection(service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_connection_status()


def order_lookup_input(order_number: str, email: str, phone: str | None = None) -> OrderLookup:
    try:
        return OrderLookup(order_number=order_number, email=email, phone=phone)
    except ValidationError as exc:
        # Do not echo private lookup values in validation messages.
        raise HTTPException(status_code=422, detail=[
            {"loc": ["query", *error["loc"]], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors(include_input=False, include_context=False)
        ]) from exc


def get_order_status_service(request: Request,
                             lookup: OrderLookup = Depends(order_lookup_input)) -> ShopifyService:
    # This nested dependency prevents settings loading if a required input is missing.
    return get_shopify_service(request)


@order_router.get("/orders/status", response_model=OrderStatusResponse,
                  response_model_exclude_unset=True,
                  responses={status: {"model": OrderLookupErrorResponse}
                             for status in (404, 409, 422, 500, 502, 503)})
async def order_status(lookup: OrderLookup = Depends(order_lookup_input),
                       service: ShopifyService = Depends(get_order_status_service)):
    order = await service.get_order_status(lookup.order_number, lookup.email, lookup.phone)
    if order is None:
        raise HTTPException(status_code=404, detail="No matching order found within the store's accessible order history")
    return order


@router.get("/policies")
async def policies(service: ShopifyService = Depends(get_shopify_service)):
    return {"policies": await service.get_policies()}


@router.get("/faq")
async def faq(service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_pages(limit=50, query="title:FAQ OR handle:faq")


router.include_router(order_router)

router.include_router(product_browsing_router)
