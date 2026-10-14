"""Derive customer-safe states from facts and render messages without an LLM."""

from collections import Counter
from urllib.parse import urlsplit

from app.messaging.order_messages import (
    DETAIL_MESSAGES, ORDER_MESSAGES, PHYSICAL_ITEM_MESSAGES, SHIPMENT_MESSAGES, SHIPMENT_STATUS_MAP,
)
from app.schemas.order_status import OrderStatusResponse

IN_MOTION = {"shipped", "out_for_delivery", "delivered"}


def item_words(items: list[dict]) -> str:
    words = [f"{item['quantity']} {item['title']}" for item in items]
    return " and ".join(words) if len(words) < 3 else ", ".join(words[:-1]) + " and " + words[-1]


def shipment_status(shipment: dict) -> str:
    if shipment["status"] == "CANCELLED":
        return "cancelled"
    if shipment["status"] in {"ERROR", "FAILURE"}:
        return "delivery_exception"
    mapped = SHIPMENT_STATUS_MAP.get(shipment.get("displayStatus"), "processing")
    if mapped in {"cancelled", "delivery_exception", "ready_for_pickup", "picked_up"}:
        return mapped
    if shipment["requiresShipping"]:
        if shipment.get("deliveredAt"):
            return "delivered"
        if mapped in IN_MOTION:
            return mapped
        if shipment.get("inTransitAt"):
            return "shipped"
    if mapped == "fulfilled":
        return "fulfilled"
    return "fulfilled" if not shipment["requiresShipping"] and shipment["status"] == "SUCCESS" else "processing"


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} and parsed.hostname else None


def format_order_status(order: dict) -> dict:
    raw_items = [x for x in order["lineItems"]["nodes"] if x["currentQuantity"] > 0]
    items = [{"title": x["title"], "quantity": x["currentQuantity"]} for x in raw_items]
    physical = {x["id"]: x["currentQuantity"] for x in raw_items if x["requiresShipping"]}
    shipped_counts: Counter = Counter()
    delivered_counts: Counter = Counter()
    out_counts: Counter = Counter()
    shipments = []
    for raw in order["fulfillments"]:
        state = shipment_status(raw)
        shipment_items = []
        for entry in raw["fulfillmentLineItems"]["nodes"]:
            shipment_items.append({"title": entry["lineItem"]["title"], "quantity": entry["quantity"]})
            if raw["requiresShipping"] and state in IN_MOTION:
                key = entry["lineItem"]["id"]
                shipped_counts[key] += entry["quantity"]
                if state == "delivered":
                    delivered_counts[key] += entry["quantity"]
                if state in {"out_for_delivery", "delivered"}:
                    out_counts[key] += entry["quantity"]
        tracking = [{"company": x.get("company"), "number": x.get("number"),
                     "url": safe_url(x.get("url"))} for x in raw["trackingInfo"]]
        shipments.append({"status": state, "items": shipment_items, "tracking": tracking})

    remaining = [{"title": x["title"], "quantity": x["currentQuantity"] - shipped_counts[x["id"]]}
                 for x in raw_items if x["id"] in physical and shipped_counts[x["id"]] < x["currentQuantity"]]
    def covers(counts):
        return bool(physical) and all(counts[key] >= quantity for key, quantity in physical.items())

    states = {shipment["status"] for shipment in shipments}
    if order.get("cancelledAt"):
        status = "cancelled"
    elif "delivery_exception" in states:
        status = "delivery_exception"
    elif covers(delivered_counts):
        status = "delivered"
    elif covers(out_counts):
        status = "out_for_delivery"
    elif covers(shipped_counts):
        status = "shipped"
    elif any(shipped_counts[key] > 0 for key in physical):
        status = "partially_shipped"
    elif order["displayFulfillmentStatus"] == "FULFILLED":
        status = "fulfilled"
    elif order["displayFulfillmentStatus"] in {"PARTIALLY_FULFILLED", "IN_PROGRESS"}:
        status = "partially_fulfilled" if order["displayFulfillmentStatus"] == "PARTIALLY_FULFILLED" else "processing"
    elif order.get("displayFinancialStatus") in {"PENDING", "PARTIALLY_PAID"}:
        status = "awaiting_payment"
    else:
        status = {"ON_HOLD": "on_hold", "SCHEDULED": "scheduled"}.get(order["displayFulfillmentStatus"], "processing")

    # Movement states describe physical items; digital items have no shipment evidence.
    described_items = items
    if status in IN_MOTION | {"partially_shipped", "delivery_exception"}:
        described_items = [{"title": x["title"], "quantity": x["currentQuantity"]}
                           for x in raw_items if x["requiresShipping"]]
    contents = f" containing {item_words(described_items)}" if described_items else ""
    templates = ORDER_MESSAGES
    if status in PHYSICAL_ITEM_MESSAGES and any(not x["requiresShipping"] for x in raw_items):
        templates = PHYSICAL_ITEM_MESSAGES
    parts = [templates[status].format(order_number=order["name"], contents=contents)]
    if status != "cancelled":
        for index, shipment in enumerate(shipments, 1):
            parts.append(SHIPMENT_MESSAGES[shipment["status"]].format(
                index=index, items=item_words(shipment["items"]) or "Items"))
            if shipment["status"] in IN_MOTION | {"delivery_exception", "processing", "fulfilled"}:
                usable = False
                for tracking in shipment["tracking"]:
                    if tracking["number"]:
                        carrier = f" ({tracking['company']})" if tracking["company"] else ""
                        parts.append(DETAIL_MESSAGES["tracking"].format(number=tracking["number"], carrier=carrier))
                        usable = True
                    if tracking["url"]:
                        parts.append(DETAIL_MESSAGES["tracking_url"].format(url=tracking["url"]))
                        usable = True
                if not usable and shipment["status"] in IN_MOTION:
                    parts.append(DETAIL_MESSAGES["tracking_pending"])
        if status == "partially_shipped" and remaining:
            parts.append(DETAIL_MESSAGES["remaining"].format(items=item_words(remaining)))
    return OrderStatusResponse(message="\n".join(parts), order_number=order["name"], status=status,
        items=items, remaining_items=remaining, shipments=shipments).model_dump()
