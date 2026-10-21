from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit

from app.clients.shopify_client import ShopifyClient
from app.clients.product_queries import (
    PRODUCT_MENU_ID, MENU_QUERY, COLLECTION_PRODUCTS_QUERY, PRODUCT_DETAILS_QUERY,
    VARIANTS_QUERY, MEMBERSHIP_QUERY, PRODUCT_COLLECTIONS_QUERY,
)
from app.messaging.product_formatter import clean_description, format_product
from app.schemas.product_browsing import (
    BrowsingError, MenuCollection, MenuCollections, ProductSummary,
    Pagination, CollectionProducts, ProductDetails, ProductVariant,
)

MAX_COLLECTION_PAGES = 10
MAX_VARIANT_PAGES = 20  # 1,000 variants, including the first page
MAX_MEMBERSHIP_PAGES = 20


def canonical_id(value: str, kind: str) -> str:
    if re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return f"gid://shopify/{kind}/{value}"
    if re.fullmatch(rf"gid://shopify/{kind}/[1-9][0-9]{{0,19}}", value):
        return value
    raise BrowsingError(422, "invalid_id", f"Provide a valid Shopify {kind.lower()} ID.")


def _not_found() -> BrowsingError:
    return BrowsingError(404, "not_found", "This product or collection is not available in the shop menu.")


def _budget() -> BrowsingError:
    return BrowsingError(503, "lookup_limit", "This selection is too large to load right now. Please try a narrower selection.")


def _next(connection: dict, previous: str | None) -> str | None:
    info = connection.get("pageInfo", {})
    if not info.get("hasNextPage"):
        return None
    cursor = info.get("endCursor")
    if not cursor or cursor == previous:
        raise BrowsingError(502, "invalid_upstream_response", "The shop could not complete this request. Please try again.")
    return cursor


def _url(value: str | None, *, image: bool = False) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    if image and not (parts.hostname == "cdn.shopify.com" or parts.hostname.endswith(".shopify.com")):
        return None
    return value


def _visible(product: dict) -> bool:
    return product.get("status") == "ACTIVE" and bool(_url(product.get("onlineStoreUrl")))


def _matches_tags(product: dict, collection: MenuCollection) -> bool:
    tags = {str(tag).casefold() for tag in product.get("tags", [])}
    return all(tag.casefold() in tags for tag in collection.tags)


def _decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError("invalid money")
        return number
    except (InvalidOperation, TypeError, ValueError):
        raise BrowsingError(502, "invalid_upstream_response", "The shop returned an invalid price. Please try again.") from None


def _summary(product: dict) -> ProductSummary:
    low = product["priceRangeV2"]["minVariantPrice"]
    high = product["priceRangeV2"]["maxVariantPrice"]
    if low["currencyCode"] != high["currencyCode"] or _decimal(low["amount"]) > _decimal(high["amount"]):
        raise BrowsingError(502, "invalid_upstream_response", "The shop returned an invalid price. Please try again.")
    image = (product.get("featuredMedia") or {}).get("image") or {}
    variants = product.get("variants", {}).get("nodes", [])
    if not variants:
        raise BrowsingError(502, "invalid_upstream_response", "The shop returned an invalid price. Please try again.")
    selected = next((v for v in variants if v.get("availableForSale")), variants[0])
    selling = selected["price"]
    _decimal(selling)
    comparison = selected.get("compareAtPrice")
    if not comparison or _decimal(comparison) <= _decimal(selling):
        comparison = None
    return ProductSummary(
        id=product["id"], title=product["title"], handle=product["handle"],
        image_url=_url(image.get("url"), image=True), image_alt=image.get("altText"),
        description=clean_description(product.get("description", ""), product.get("descriptionHtml", "")),
        price=selling, currency=low["currencyCode"],
        compare_at_price=comparison, on_sale=comparison is not None,
        product_url=product["onlineStoreUrl"],
    )


class ProductBrowsingService:
    def __init__(self, client: ShopifyClient):
        self.client = client

    async def _load_variants(self, product: dict, *, complete: bool) -> None:
        """Details need all variants; listing needs enough to find the first available."""
        connection = product["variants"]
        variants = list(connection["nodes"])
        after = _next(connection, None)
        for _ in range(MAX_VARIANT_PAGES - 1):
            if after is None or (not complete and any(v.get("availableForSale") for v in variants)):
                break
            data = await self.client.query_with_retry(VARIANTS_QUERY, {"productId": product["id"], "after": after})
            if not data.get("product"):
                raise _not_found()
            connection = data["product"]["variants"]
            variants.extend(connection["nodes"])
            after = _next(connection, after)
        if after and (complete or not any(v.get("availableForSale") for v in variants)):
            raise _budget()
        product["variants"] = {"nodes": variants, "pageInfo": {"hasNextPage": after is not None, "endCursor": after}}

    async def collections(self) -> MenuCollections:
        data = await self.client.query_with_retry(MENU_QUERY, {"menuId": PRODUCT_MENU_ID})
        menu = data.get("menu")
        if menu is None:
            raise BrowsingError(502, "menu_unavailable", "The configured shop menu is unavailable. Please contact support.")
        found: dict[str, MenuCollection] = {}

        def visit(items: list[dict]) -> None:
            for item in items:
                resource = item.get("resourceId", "")
                if item.get("type") == "COLLECTION" and isinstance(resource, str) and re.fullmatch(r"gid://shopify/Collection/[1-9][0-9]{0,19}", resource):
                    if resource not in found:
                        found[resource] = MenuCollection(id=resource, title=item["title"], url=item.get("url"), tags=item.get("tags") or [])
                visit(item.get("items") or [])

        visit(menu.get("items") or [])
        return MenuCollections(menu_id=PRODUCT_MENU_ID, menu_title=menu["title"], total=len(found), collections=list(found.values()))

    async def collection_products(self, collection_id: str, limit: int = 10, cursor: str | None = None) -> CollectionProducts:
        collection_id = canonical_id(collection_id, "Collection")
        if not 1 <= limit <= 50:
            raise BrowsingError(422, "invalid_limit", "Limit must be between 1 and 50.")
        allowed = {c.id: c for c in (await self.collections()).collections}
        if collection_id not in allowed:
            raise _not_found()
        selection = allowed[collection_id]
        result: list[ProductSummary] = []
        after = cursor
        for _ in range(MAX_COLLECTION_PAGES):
            data = await self.client.query_with_retry(COLLECTION_PRODUCTS_QUERY, {
                "collectionId": collection_id, "first": min(10, limit - len(result)), "after": after,
            })
            collection = data.get("collection")
            if not collection:
                raise _not_found()
            connection = collection["products"]
            for edge in connection["edges"]:
                product = edge["node"]
                if _visible(product) and _matches_tags(product, selection):
                    await self._load_variants(product, complete=False)
                    result.append(_summary(product))
            after = _next(connection, after)
            if after is None or len(result) >= limit:
                break
        # At the scan budget return a resumable (possibly empty) page, never skip.
        return CollectionProducts(collection_id=collection_id, collection_title=selection.title,
                                  products=result, pagination=Pagination(has_next_page=after is not None, next_cursor=after))

    async def _membership(self, product: dict, allowed: list[MenuCollection], context: str | None) -> bool:
        candidates = {c.id: c for c in allowed if _matches_tags(product, c)}
        if context:
            if context not in candidates:
                return False
            data = await self.client.query_with_retry(MEMBERSHIP_QUERY, {"productId": product["id"], "collectionId": context})
            return bool((data.get("product") or {}).get("inCollection"))
        if not candidates:
            return False
        after = None
        for _ in range(MAX_MEMBERSHIP_PAGES):
            data = await self.client.query_with_retry(PRODUCT_COLLECTIONS_QUERY, {"productId": product["id"], "after": after})
            if not data.get("product"):
                return False
            connection = data["product"]["collections"]
            if any(c["id"] in candidates for c in connection["nodes"]):
                return True
            after = _next(connection, after)
            if after is None:
                return False
        raise _budget()

    async def product_details(self, product_id: str, collection_id: str | None = None) -> ProductDetails:
        product_id = canonical_id(product_id, "Product")
        context = canonical_id(collection_id, "Collection") if collection_id else None
        allowed = (await self.collections()).collections
        if context and context not in {c.id for c in allowed}:
            raise _not_found()
        data = await self.client.query_with_retry(PRODUCT_DETAILS_QUERY, {"productId": product_id})
        product = data.get("product")
        if not product or not _visible(product):
            raise _not_found()
        await self._load_variants(product, complete=True)
        variants = product["variants"]["nodes"]
        if not await self._membership(product, allowed, context):
            raise _not_found()
        product["variants"] = {"nodes": variants, "pageInfo": {"hasNextPage": False}}
        summary = _summary(product)
        mapped = []
        for v in variants:
            _decimal(v["price"])
            original = v.get("compareAtPrice")
            if not original or _decimal(original) <= _decimal(v["price"]):
                original = None
            mapped.append(ProductVariant(id=v["id"], title=v["title"], price=v["price"],
                                         compare_at_price=original, available=v["availableForSale"],
                                         selected_options=v.get("selectedOptions", [])))
        result = ProductDetails(**summary.model_dump(), vendor=product.get("vendor", ""), product_type=product.get("productType", ""),
                                available=any(v.available for v in mapped), variants=mapped, whatsapp_message="")
        result.whatsapp_message = format_product(result)
        return result
