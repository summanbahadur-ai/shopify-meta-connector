from app.messaging.product_card_formatter import build_product_card
from app.schemas.product_card import CardProduct, ProductCardResponse


class ProductCardService:
    def __init__(self, browsing, whatchimp):
        self.browsing, self.whatchimp = browsing, whatchimp

    async def submit(self, request):
        # Details enforce menu membership, tag restrictions and publication visibility.
        details = await self.browsing.product_details(request.product_id)
        card = build_product_card(details)
        await self.whatchimp.send_card(request.phone_number, card)
        facts = details.model_dump()
        facts["on_sale"] = card["on_sale"]
        return ProductCardResponse(phone_number=request.phone_number, product=CardProduct(**facts))
