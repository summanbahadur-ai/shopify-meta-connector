from app.messaging.product_carousel_formatter import build_carousel_card
from app.schemas.product_card import CardError
from app.schemas.product_carousel import ProductCarouselPreview
from app.schemas.product_browsing import Pagination

MAX_CAROUSEL_COLLECTION_PAGES = 20


class ProductCarouselService:
    def __init__(self, browsing):
        self.browsing = browsing

    async def submit(self, request):
        # No guessed WhatChimp URL, template components or credentials sent.
        if not request.dry_run:
            raise CardError(501, "carousel_send_unconfigured",
                "Carousel sending requires a verified WhatChimp carousel API example. Use dry_run=true to preview Shopify cards.")
        cards = []
        cursor = request.cursor
        seen_cursors = {cursor} if cursor else set()
        seen_products = set()
        for _ in range(MAX_CAROUSEL_COLLECTION_PAGES):
            batch = await self.browsing.collection_products(request.collection_id,
                limit=request.limit - len(cards), cursor=cursor)
            for product in batch.products:
                if product.id in seen_products:
                    continue
                seen_products.add(product.id)
                if not product.image_url:
                    continue
                details = await self.browsing.product_details(product.id, request.collection_id)
                variant = next((v for v in details.variants if v.id == details.variant_id), None)
                if not details.image_url or not variant or not variant.available:
                    continue
                if details.variant_id != product.variant_id:
                    raise CardError(409, "product_changed", "A product changed. Reload the collection before preparing the carousel.")
                cards.append(build_carousel_card(details))
            if not batch.pagination.has_next_page:
                cursor = None
                break
            cursor = batch.pagination.next_cursor
            if not cursor or cursor in seen_cursors:
                raise CardError(502, "invalid_pagination", "The shop could not complete this collection.")
            seen_cursors.add(cursor)
            if len(cards) >= request.limit:
                break
        if len(cards) < 2:
            if cursor:
                raise CardError(503, "collection_limit", "This collection could not supply enough carousel cards within the lookup limit.")
            raise CardError(422, "insufficient_carousel_products", "A carousel requires at least two available products with images.")
        return ProductCarouselPreview(collection_id=request.collection_id.rsplit("/", 1)[-1],
            count=len(cards), cards=cards,
            pagination=Pagination(has_next_page=cursor is not None, next_cursor=cursor))
