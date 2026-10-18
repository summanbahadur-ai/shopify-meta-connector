from __future__ import annotations

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.dependencies import get_shopify_service
from app.api.order_errors import OrderStatusRoute
from app.services.shopify_service import ShopifyService
from app.schemas.order_status import OrderLookup, OrderLookupErrorResponse, OrderStatusResponse

router = APIRouter(prefix="/shopify", tags=["Shopify"])
order_router = APIRouter(route_class=OrderStatusRoute)


@router.get("/connection")
async def connection(service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_connection_status()


@router.get("/shop")
async def shop(service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_shop()


@router.get("/products")
async def products(limit: int = Query(50, ge=1, le=100), after: str | None = None, service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_products(limit, after)


@router.get("/products/export.csv")
async def export_products(service: ShopifyService = Depends(get_shopify_service)):
    products = await service.get_all_products()
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["product_id", "title", "handle", "vendor", "product_type", "status", "variant_id", "variant_title", "sku", "barcode", "price", "compare_at_price"])
    for product in products:
        variants = product.get("variants", {}).get("nodes", []) or [{}]
        for variant in variants:
            writer.writerow([
                product.get("id"), product.get("title"), product.get("handle"), product.get("vendor"),
                product.get("productType"), product.get("status"), variant.get("id"), variant.get("title"),
                variant.get("sku"), variant.get("barcode"), variant.get("price"), variant.get("compareAtPrice")
            ])
    stream.seek(0)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=shopify-product-catalog.csv"})


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


@router.get("/pages")
async def pages(limit: int = Query(50, ge=1, le=100), after: str | None = None, query: str | None = None, service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_pages(limit, after, query)


@router.get("/faq")
async def faq(service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_pages(limit=50, query="title:FAQ OR handle:faq")


router.include_router(order_router)
