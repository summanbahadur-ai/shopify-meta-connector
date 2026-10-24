from decimal import Decimal, ROUND_HALF_UP
import re
from app.messaging.product_formatter import clean_description
from app.messaging.button_details_messages import LABELS as L, IN_STOCK, OUT_OF_STOCK, DESCRIPTION_LIMIT, MESSAGE_LIMIT


def _money(value, currency):
    amount = format(Decimal(value), ",f")
    if "." in amount:
        amount = amount.rstrip("0").rstrip(".")
    return f"{currency} {amount}"


def format_button_details(product, reviews=None):
    title = re.sub(r"[*_~`\r\n]", " ", product.title).strip()[:200]
    parts = [f"*{title}*", f"*{L['price']}:* {_money(product.price, product.currency)}"]
    selling = Decimal(product.price)
    original = Decimal(product.compare_at_price) if product.compare_at_price else None
    if original is not None and original > selling:
        discount = ((original - selling) / original * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        parts.extend([f"*{L['offer']}:* {discount.normalize():f}% OFF",
                      f"*{L['original']}:* {_money(product.compare_at_price, product.currency)}"])
    description = clean_description(product.description, "")
    if description:
        if len(description) > DESCRIPTION_LIMIT:
            description = description[:DESCRIPTION_LIMIT - 3].rstrip() + "..."
        parts.append(f"*{L['description']}*\n{description}")
    if reviews is not None:
        parts.append(f"*{L['reviews']}*\nRating: {reviews.rating}/{reviews.scale} ({reviews.count} reviews)")
    parts.append(f"*{L['availability']}*\n{IN_STOCK if product.available else OUT_OF_STOCK}")
    return "\n\n".join(parts)[:MESSAGE_LIMIT]
