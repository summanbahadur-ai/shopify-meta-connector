from app.messaging.product_card_formatter import build_product_card
from app.schemas.product_card import CardError, CardProduct, ProductCardResponse

MAX_CARD_COLLECTION_PAGES = 20


class ProductCardService:
    def __init__(self, browsing, whatchimp):
        self.browsing, self.whatchimp = browsing, whatchimp

    async def submit(self, request):
        products = []
        cursor = None
        seen_cursors = set()
        for _ in range(MAX_CARD_COLLECTION_PAGES):
            batch = await self.browsing.collection_products(request.collection_id, limit=50, cursor=cursor)
            products.extend(batch.products)
            if not batch.pagination.has_next_page:
                break
            cursor = batch.pagination.next_cursor
            if not cursor or cursor in seen_cursors:
                raise CardError(502, "invalid_pagination", "The shop could not complete this collection.")
            seen_cursors.add(cursor)
        else:
            raise CardError(503, "collection_limit", "This collection is too large to load a product card.")
        if not products:
            raise CardError(404, "empty_collection", "This collection has no available product information.")
        if request.product_index >= len(products):
            raise CardError(404, "product_index_out_of_range", "There is no product at this position.")
        product = products[request.product_index]
        details = await self.browsing.product_details(product.id, request.collection_id)
        variant = next((v for v in details.variants if v.id == product.variant_id), None)
        if variant is None or not variant.available:
            raise CardError(409, "variant_unavailable", "This product variant is currently unavailable.")
        # Use fresh details and their matching price/variant pair after the availability check.
        if details.variant_id != product.variant_id:
            raise CardError(409, "product_changed", "This product changed. Reload the collection before sending.")
        card = build_product_card(details, request.product_index, len(products), collection_id=request.collection_id)
        await self.whatchimp.send_card(request.phone_number, card)
        return ProductCardResponse(phone_number=request.phone_number,
            collection_id=request.collection_id.rsplit("/", 1)[-1], product_index=request.product_index,
            product=CardProduct(**details.model_dump()))
