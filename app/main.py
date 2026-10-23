from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.product_card import router as product_card_router
from app.api.product_carousel import router as product_carousel_router
from app.core.config import ConfigurationError
from app.core.exceptions import AmbiguousOrderError, OrderLookupLimitError, ShopifyAuthenticationError, ShopifyAPIError

app = FastAPI(
    title="Shopify Meta Connector",
    version="0.1.0",
    description="Shopify data API foundation for a future Meta WhatsApp commerce assistant.",
)
app.include_router(api_router)
app.include_router(product_card_router)
app.include_router(product_carousel_router)


@app.get("/")
async def root():
    return {"service": "shopify-meta-connector", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(ConfigurationError)
async def configuration_error(_: Request, exc: ConfigurationError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(ShopifyAuthenticationError)
async def authentication_error(_: Request, exc: ShopifyAuthenticationError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ShopifyAPIError)
async def shopify_error(_: Request, exc: ShopifyAPIError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(AmbiguousOrderError)
async def ambiguous_order(_: Request, exc: AmbiguousOrderError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(OrderLookupLimitError)
async def order_lookup_limit(_: Request, exc: OrderLookupLimitError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})
