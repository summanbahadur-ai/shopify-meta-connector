from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit
from app.messaging import product_card_messages as M
from app.messaging.product_formatter import clean_description
from app.schemas.product_card import CardError

CAPTION_LIMIT = 1024


def _amount(value):
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError()
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise CardError(502, "invalid_product", "The shop returned invalid product pricing.") from None


def _money(amount, currency):
    value = format(amount, ",f")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return currency + " " + value


def build_product_card(product):
    title = re.sub(r"[*_~`\n\r]", " ", product.title).strip()[:160]
    url = product.product_url
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in url):
        raise CardError(502, "invalid_product", "The shop returned an invalid product link.")
    price = _amount(product.price)
    original = _amount(product.compare_at_price) if product.compare_at_price else None
    sale = original is not None and original > price
    heading = [f"*{title}*", f"*{M.CURRENT_PRICE_LABEL}:* {_money(price, product.currency)}",
               f"*{M.SALE_LABEL}:* {M.YES if sale else M.NO}"]
    if sale:
        heading.append(f"*{M.ORIGINAL_LABEL}:* {_money(original, product.currency)}")
    heading.append(M.AVAILABLE if product.available else M.UNAVAILABLE)
    top = "\n\n".join(heading)
    bottom = f"\n\n*{M.SHOP_LABEL}*\n{url}"
    remaining = CAPTION_LIMIT - len(top) - len(bottom)
    if remaining < 0:
        raise CardError(422, "product_caption_limit", "The product link is too long for a product card.")
    description = clean_description(product.description, "")
    label = f"\n\n*{M.DESCRIPTION_LABEL}*\n"
    section = ""
    if description and remaining > len(label) + 3:
        room = remaining - len(label)
        if len(description) > room:
            description = description[:room - 3].rstrip() + "..."
        section = label + description
    return {"message": top + section + bottom, "media_url": product.image_url, "on_sale": sale}
