from decimal import Decimal
import re
from app.messaging import product_card_messages as M
from app.schemas.product_card import CardError


def build_product_card(product, product_index, total_products, *, collection_id=None):
    if product.currency != "PKR":
        raise CardError(422, "unsupported_currency", "Product cards require Shopify prices in PKR.")
    product_id = product.id.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[1-9][0-9]{0,19}", product_id):
        raise CardError(502, "invalid_product", "The shop returned an invalid product.")
    title = re.sub(r"[*_~`\n\r]", " ", product.title).strip()[:200]
    price = format(Decimal(product.price), ",f")
    if "." in price:
        price = price.rstrip("0").rstrip(".")
    parts = [f"*{title}*", f"{M.PRICE_LABEL}: PKR {price}"]
    parts.append(M.POSITION.format(position=product_index + 1, total=total_products))
    buttons = [{"id": f"DETAILS:{product_id}", "title": M.DETAILS_TITLE},
               {"id": f"ADD:{product_id}", "title": M.ADD_TITLE}]
    if product_index + 1 < total_products:
        if collection_id is None:
            raise CardError(422, "missing_context", "Collection context is required for navigation.")
        numeric = collection_id.rsplit("/", 1)[-1]
        buttons.append({"id": f"NEXT:{numeric}:{product_index + 1}", "title": M.NEXT_TITLE})
    else:
        buttons.append({"id": "CATEGORIES:1", "title": M.BACK_TITLE})
    if any(len(b["id"]) > 256 or len(b["title"]) > 20 for b in buttons):
        raise CardError(422, "invalid_buttons", "The product navigation could not be built.")
    payload = {"message": "\n\n".join(parts), "buttons": buttons, "button_footer_text": M.FOOTER}
    if product.image_url:
        payload["media_url"] = product.image_url
    else:
        payload["button_header_text"] = title[:60]
    return payload
