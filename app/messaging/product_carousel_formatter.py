from decimal import Decimal
import re
from app.messaging import product_card_messages as M
from app.schemas.product_card import CardError
from app.schemas.product_carousel import CarouselCard


def build_carousel_card(product):
    if product.currency != "PKR":
        raise CardError(422, "unsupported_currency", "Product carousels require Shopify prices in PKR.")
    identifier = product.id.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
        raise CardError(502, "invalid_product", "The shop returned an invalid product.")
    value = Decimal(product.price)
    if not value.is_finite() or value < 0:
        raise CardError(502, "invalid_price", "The shop returned an invalid product price.")
    price = format(value, ",f")
    if "." in price:
        price = price.rstrip("0").rstrip(".")
    price_line = f"{M.PRICE_LABEL}: PKR {price}"
    title = re.sub(r"[*_~`\n\r]", " ", product.title).strip()
    title_limit = 160 - len(price_line) - 1
    if title_limit < 1:
        raise CardError(502, "invalid_price", "The shop returned an invalid product price.")
    body = title[:title_limit] + "\n" + price_line
    return CarouselCard(product_id=product.id, variant_id=product.variant_id,
        title=product.title, price=product.price, currency=product.currency,
        media_url=product.image_url, body=body,
        buttons=[{"id": f"DETAILS:{identifier}", "title": M.DETAILS_TITLE},
                 {"id": f"ADD:{identifier}", "title": M.ADD_TITLE}])
