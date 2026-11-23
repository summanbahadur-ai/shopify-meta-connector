from app.clients.whatchimp_client import WhatChimpClient


class WhatChimpTextClient(WhatChimpClient):
    async def send_text(self, phone_number, message):
        return await self._send_message({"to": "+" + phone_number.lstrip("+"), "text": message})
