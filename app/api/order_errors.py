"""Order-only HTTP boundary: catch failures including dependency/validation errors.

Business/transport layers retain typed exceptions. Only curated messages and
stable codes cross this boundary. Never log exception text or lookup values.
"""

import logging

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.core.exceptions import (
    AmbiguousOrderError, OrderLookupLimitError, ShopifyAPIError, ShopifyAuthenticationError,
)
from app.messaging.order_messages import LOOKUP_ERROR_MESSAGES
from app.schemas.order_status import OrderInputIssue, OrderLookupErrorResponse

logger = logging.getLogger(__name__)


def error_response(status: int, code: str, issues: list[OrderInputIssue] | None = None) -> JSONResponse:
    message = " ".join(dict.fromkeys(issue.message for issue in issues)) if issues else LOOKUP_ERROR_MESSAGES[code]
    payload = OrderLookupErrorResponse(code=code, message=message, errors=issues or [])
    return JSONResponse(status_code=status, content=payload.model_dump())


def validation_response(errors: list[dict]) -> JSONResponse:
    issues = []
    for error in errors:
        location = error.get("loc", ())
        field = str(location[-1]) if location else "input"
        if field in {"order_number", "email", "phone"}:
            prefix = "missing" if error.get("type") == "missing" else "invalid"
            code = f"{prefix}_{field}"
        else:
            code = "invalid_input"
        # A phone is optional; malformed transport inputs still have a generic fallback.
        if code not in LOOKUP_ERROR_MESSAGES:
            code = "invalid_input"
        issues.append(OrderInputIssue(field=field, code=code, message=LOOKUP_ERROR_MESSAGES[code]))
    return error_response(422, issues[0].code if issues else "invalid_input", issues)


class OrderStatusRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_order_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return validation_response(exc.errors())
            except HTTPException as exc:
                if exc.status_code == 422 and isinstance(exc.detail, list):
                    return validation_response(exc.detail)
                if exc.status_code == 404:
                    return error_response(404, "order_not_found")
                return error_response(exc.status_code, "service_unavailable")
            except AmbiguousOrderError:
                return error_response(409, "multiple_orders")
            except OrderLookupLimitError:
                return error_response(503, "lookup_limit")
            except (ShopifyAPIError, ShopifyAuthenticationError) as exc:
                logger.warning("Order lookup upstream failure: %s", type(exc).__name__)
                return error_response(502, "service_unavailable")
            except Exception as exc:
                # Includes configuration, unexpected service, and response-validation errors.
                # Do not include exc/traceback: they can contain contacts or credentials.
                logger.error("Order lookup internal failure: %s", type(exc).__name__)
                return error_response(500, "service_unavailable")

        return safe_order_handler
