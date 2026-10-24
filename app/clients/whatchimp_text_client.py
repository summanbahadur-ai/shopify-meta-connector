import httpx
from app.clients.whatchimp_client import WhatChimpClient, redact_response
from app.schemas.product_card import CardError


class WhatChimpTextClient(WhatChimpClient):
    async def send_text(self, phone_number, message):
        fields = {"apiToken": self.settings.api_token, "phone_number_id": self.settings.phone_number_id,
                  "phone_number": phone_number, "message": message}
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=self.transport) as client:
                response = await client.post(self.settings.base_url + "/whatsapp/send", data=fields)
        except httpx.TimeoutException:
            raise CardError(504, "whatchimp_timeout", "Send status is unknown. Check WhatChimp before retrying.") from None
        except httpx.RequestError:
            raise CardError(502, "whatchimp_connection", "Send status is unknown. Check WhatChimp before retrying.") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        self.last_diagnostics = {"http_status": response.status_code, "response": redact_response(data)}
        if response.status_code in (401, 403):
            raise CardError(502, "whatchimp_authentication", "WhatChimp rejected the server credentials.")
        if response.status_code == 429:
            raise CardError(429, "whatchimp_rate_limit", "WhatChimp is rate limiting requests.")
        if not response.is_success or not isinstance(data, dict) or type(data.get("status")) not in (str, int) or str(data.get("status")) != "1":
            raise CardError(502, "whatchimp_rejected", "WhatChimp did not acknowledge the text message.")
        return self.last_diagnostics
