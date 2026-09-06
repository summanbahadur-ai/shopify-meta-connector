from __future__ import annotations

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_shopify_service
from app.services.shopify_service import ShopifyService

router = APIRouter(prefix="/shopify", tags=["Shopify"])


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


@router.get("/orders")
async def orders(limit: int = Query(20, ge=1, le=100), after: str | None = None, query: str | None = None, service: ShopifyService = Depends(get_shopify_service)):
    return await service.get_orders(limit, after, query)


@router.get("/orders/status")
async def order_status(order_number: str, service: ShopifyService = Depends(get_shopify_service)):
    order = await service.get_order_status(order_number)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
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
