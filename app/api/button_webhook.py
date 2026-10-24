"""Only the manually configured View Details button webhook. No global receiver."""
import hashlib
import json
import logging
import re
from urllib.parse import parse_qs
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from app.api.dependencies import get_shopify_service
from app.clients.whatchimp_text_client import WhatChimpTextClient
from app.core.config import ButtonWebhookSettings, WhatChimpSettings, ConfigurationError
from app.core.exceptions import ShopifyAPIError, ShopifyAuthenticationError
from app.schemas.product_card import CardError
from app.schemas.product_browsing import BrowsingError
from app.schemas.button_webhook import ButtonWebhookError, ButtonClickPayload
from app.services.button_identity import identify_customer
from app.services.button_state import D1ButtonState, local_state
from app.services.button_webhook import ButtonDetailsService
from app.services.product_browsing import ProductBrowsingService
from app.services.product_reviews import ProductReviewService

logger = logging.getLogger(__name__)
PATH = "/api/whatsapp/button-click"
MAX_BODY_BYTES = 65536


class ButtonURLLogFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"([?&]token=)[^&\s\"']*", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


for name in ("httpx", "uvicorn.access", "uvicorn.error"):
    logging.getLogger(name).addFilter(ButtonURLLogFilter())


class ButtonURLPrivacy:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").rstrip("/") == PATH:
            query = scope.get("query_string", b"")
            scope["query_string"] = b""
            scope["raw_path"] = scope.get("path", "").encode()
            values = {}
            if len(query) <= 8192:
                try:
                    values = parse_qs(query.decode("ascii"), keep_blank_values=True, max_num_fields=50)
                except (ValueError, UnicodeError):
                    pass
            values.pop("token", None)
            scope["button_query"] = {key: value[0] if len(value) == 1 else value for key, value in values.items()}
        await self.app(scope, receive, send)


class ButtonWebhookRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except ButtonWebhookError as exc:
                error = exc
            except ConfigurationError:
                error = ButtonWebhookError(503, "configuration_error", "Button webhook configuration is incomplete.")
            except BrowsingError as exc:
                error = ButtonWebhookError(exc.status, exc.code, exc.message)
            except CardError as exc:
                error = ButtonWebhookError(exc.status, exc.code, exc.message)
            except (ShopifyAPIError, ShopifyAuthenticationError):
                error = ButtonWebhookError(502, "shopify_unavailable", "Shopify could not load this product.")
            except Exception:
                error = ButtonWebhookError(503, "button_webhook_unavailable", "Button processing is unavailable. Check send status before retrying.")
            logger.warning("Button webhook failure: %s", error.code)
            return JSONResponse(status_code=error.status, content={"success": False, "code": error.code, "message": error.message})
        return safe_handler


async def parse_button_request(request: Request):
    settings = ButtonWebhookSettings.from_source(request.scope.get("env"))
    query = request.scope.get("button_query", {})
    try:
        payload = ButtonClickPayload.model_validate({name: query.get(name) for name in ("product_id", "action")})
    except ValidationError:
        raise ButtonWebhookError(422, "invalid_button_request", "Provide a valid product_id and action=view_details.") from None
    env = request.scope.get("env")
    database = env.get("WHATCHIMP_BUTTON_STATE") if isinstance(env, dict) else getattr(env, "WHATCHIMP_BUTTON_STATE", None) if env is not None else None
    state = D1ButtonState(database) if database is not None else local_state
    # This public callback is rate limited per product, independent of recipient.
    rate_key = "product:" + hashlib.sha256(payload.product_id.encode()).hexdigest()
    if not await state.allow(rate_key, settings.rate_limit):
        raise ButtonWebhookError(429, "button_rate_limit", "Too many product-details requests. Try later.")
    return settings, payload, state


def get_button_service(request: Request, auth=Depends(parse_button_request)):
    settings, payload, state = auth
    shopify = get_shopify_service(request).client
    return ButtonDetailsService(ProductBrowsingService(shopify),
        WhatChimpTextClient(WhatChimpSettings.from_request(request)), ProductReviewService(shopify, settings), state, settings), payload


async def read_payload(request):
    body = bytearray()
    length = request.headers.get("content-length")
    try:
        if length and int(length) > MAX_BODY_BYTES:
            raise ButtonWebhookError(413, "payload_too_large", "Webhook payload is too large.")
        if length and int(length) < 0:
            raise ValueError()
    except ValueError:
        raise ButtonWebhookError(400, "invalid_body", "Invalid webhook request body.") from None
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise ButtonWebhookError(413, "payload_too_large", "Webhook payload is too large.")
        body.extend(chunk)
    if not body:
        return {}, "empty"
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        if media == "application/json" or media.startswith("application/") and media.endswith("+json"):
            return json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError())), "json"
        if media == "application/x-www-form-urlencoded":
            values = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=100)
            return {key: value[0] if len(value) == 1 else value for key, value in values.items()}, "form"
    except (ValueError, UnicodeError, RecursionError):
        raise ButtonWebhookError(400, "invalid_body", "Invalid webhook request body.") from None
    raise ButtonWebhookError(415, "unsupported_content_type", "Use JSON or form-encoded webhook data.")


router = APIRouter(prefix="/api/whatsapp", tags=["Product button webhook"], route_class=ButtonWebhookRoute)
QUERY_DOCS = {"parameters": [
    {"name": "product_id", "in": "query", "required": True, "schema": {"type": "string"}},
    {"name": "action", "in": "query", "required": True, "schema": {"type": "string", "enum": ["view_details"]}},
]}


@router.get("/button-click", operation_id="button_click_get", openapi_extra=QUERY_DOCS)
@router.post("/button-click", operation_id="button_click_post", openapi_extra=QUERY_DOCS)
async def button_click(request: Request, context=Depends(get_button_service)):
    service, payload = context
    body, _ = await read_payload(request)
    query = request.scope.pop("button_query", {})
    identity = identify_customer(body, query, service.settings)
    return await service.handle(payload, identity)
