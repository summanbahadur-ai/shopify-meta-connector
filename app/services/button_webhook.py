import hashlib
from app.schemas.button_webhook import ButtonWebhookError
from app.messaging.button_details_formatter import format_button_details


class ButtonDetailsService:
    def __init__(self, browsing, sender, reviews, state, settings):
        self.browsing, self.sender, self.reviews, self.state, self.settings = browsing, sender, reviews, state, settings

    async def handle(self, payload, identity):
        acknowledgement = {"success": True, "action": payload.action, "product_id": payload.product_id,
                           "customer_identified": identity.phone is not None}
        if not identity.phone:
            raise ButtonWebhookError(422, "customer_not_identified", "No customer phone number is available. No message sent.")
        context = identity.phone + ":" + payload.product_id
        claim = ("event:" + identity.event_id + ":" + context) if identity.event_id else ("click:" + context)
        state_key = hashlib.sha256(claim.encode()).hexdigest()
        # Claim before external work. Retain on all failures to prevent ambiguous retry sends.
        if not await self.state.claim(state_key, 86400 if identity.event_id else 10):
            return {**acknowledgement, "mode": "duplicate", "submitted": False}
        product = await self.browsing.product_details(payload.product_id)
        try:
            reviews = await self.reviews.get(product.id)
        except Exception:
            reviews = None
        message = format_button_details(product, reviews)
        await self.sender.send_text(identity.phone, message)
        return {**acknowledgement, "mode": "submitted", "submitted": True,
                "message": "Product details submitted to WhatChimp; delivery is not confirmed."}
