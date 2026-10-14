"""Extend natural-language copy here without changing Shopify or HTTP code.

Keys are stable application states; values are deterministic English templates.
Shopify-to-application mappings are separate from customer wording.
"""

SHIPMENT_STATUS_MAP = {
    "IN_TRANSIT": "shipped",
    "CARRIER_PICKED_UP": "shipped",
    "OUT_FOR_DELIVERY": "out_for_delivery",
    "DELIVERED": "delivered",
    "ATTEMPTED_DELIVERY": "delivery_exception",
    "FAILURE": "delivery_exception",
    "DELAYED": "delivery_exception",
    "NOT_DELIVERED": "delivery_exception",
    "CANCELED": "cancelled",
    "CONFIRMED": "processing",
    "LABEL_PRINTED": "processing",
    "LABEL_PURCHASED": "processing",
    "LABEL_VOIDED": "cancelled",
    "MARKED_AS_FULFILLED": "fulfilled",
    "FULFILLED": "fulfilled",
    "SUBMITTED": "processing",
    "READY_FOR_PICKUP": "ready_for_pickup",
    "PICKED_UP": "picked_up",
}

ORDER_MESSAGES = {
    "processing": "Your order {order_number}{contents} is being processed.",
    "awaiting_payment": "Your order {order_number}{contents} is awaiting payment.",
    "cancelled": "Your order {order_number} has been cancelled.",
    "on_hold": "Your order {order_number}{contents} is on hold.",
    "scheduled": "Your order {order_number}{contents} is scheduled for fulfillment.",
    "fulfilled": "Your order {order_number}{contents} has been fulfilled.",
    "partially_fulfilled": "Your order {order_number}{contents} has been partially fulfilled.",
    "partially_shipped": "Your order {order_number}{contents} has partially shipped.",
    "shipped": "Your order {order_number}{contents} has shipped.",
    "out_for_delivery": "Your order {order_number}{contents} is out for delivery.",
    "delivered": "Your order {order_number}{contents} has been delivered.",
    "delivery_exception": "Your order {order_number}{contents} has a delivery issue.",
}

# For mixed digital/physical orders, movement describes physical items only.
PHYSICAL_ITEM_MESSAGES = {
    "partially_shipped": "The physical items in your order {order_number}{contents} have partially shipped.",
    "shipped": "The physical items in your order {order_number}{contents} have shipped.",
    "out_for_delivery": "The physical items in your order {order_number}{contents} are out for delivery.",
    "delivered": "The physical items in your order {order_number}{contents} have been delivered.",
    "delivery_exception": "The physical items in your order {order_number}{contents} have a delivery issue.",
}

SHIPMENT_MESSAGES = {
    "processing": "Shipment {index}: {items} is being prepared.",
    "fulfilled": "Shipment {index}: {items} has been fulfilled.",
    "shipped": "Shipment {index}: {items} has shipped.",
    "out_for_delivery": "Shipment {index}: {items} is out for delivery.",
    "delivered": "Shipment {index}: {items} has been delivered.",
    "delivery_exception": "Shipment {index}: {items} has a delivery issue.",
    "cancelled": "Shipment {index}: {items} has been cancelled.",
    "ready_for_pickup": "Shipment {index}: {items} is ready for pickup.",
    "picked_up": "Shipment {index}: {items} has been picked up.",
}

DETAIL_MESSAGES = {
    "remaining": "Not yet shipped: {items}.",
    "tracking": "Tracking number: {number}{carrier}.",
    "tracking_url": "Track it here: {url}",
    "tracking_pending": "Tracking information is not yet available.",
}
