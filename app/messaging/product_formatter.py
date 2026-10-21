from decimal import Decimal
from html.parser import HTMLParser
import re

from app.messaging.product_messages import CURRENCY_LABELS, MESSAGE_VARIANT_LIMIT, PRODUCT_LABELS as L
from app.schemas.product_browsing import ProductDetails


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template"):
            self.blocked.append(tag)
        if not self.blocked and tag in ("p", "div", "br", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def clean_description(description: str, html: str) -> str:
    # Prefer the HTML source when present so script/style contents can be removed.
    parser = _TextParser()
    parser.feed(html or description)
    return "\n".join(line for raw in "".join(parser.parts).splitlines()
                     if (line := re.sub(r"\s+", " ", raw).strip()))


def money(amount: str, currency: str) -> str:
    value = f"{Decimal(amount):,f}"
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return f"{CURRENCY_LABELS.get(currency, currency)} {value}"


def format_product(product: ProductDetails) -> str:
    price = money(product.price, product.currency)
    paragraphs = [product.title, f"{L['price']}: {price}"]
    if product.compare_at_price:
        paragraphs.append(f"{L['original']}: {money(product.compare_at_price, product.currency)}")
    if product.description:
        paragraphs.append(f"{L['description']}:\n{product.description}")
    available = [v for v in product.variants if v.available]
    if available:
        options = [f"• {v.title}: {money(v.price, product.currency)}"
                   for v in available[:MESSAGE_VARIANT_LIMIT]]
        paragraphs.append(L["variants"] + ":\n" + "\n".join(options))
        if len(available) > MESSAGE_VARIANT_LIMIT:
            paragraphs.append(L["more_options"])
    else:
        paragraphs.append(L["unavailable"])
    paragraphs.append(f"{L['link']}:\n{product.product_url}")
    return "\n\n".join(paragraphs)
