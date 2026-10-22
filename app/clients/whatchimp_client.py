import json
import httpx
from app.schemas.product_card import CardError


def redact_response(value):
    """Retain structure, never arbitrary upstream strings/echoed secrets or contacts."""
    if isinstance(value, dict):
        return {str(k) if str(k) in {"status", "message", "wa_message_id", "data", "error", "code"} else "redacted_field_" + str(i):
                redact_response(v) for i, (k, v) in enumerate(value.items())}
    if isinstance(value, list):
        return [redact_response(v) for v in value[:20]]
    return "[redacted]"


class WhatChimpClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self.last_diagnostics = None

    async def send_card(self, phone_number, card):
        fields = {**card, "apiToken": self.settings.api_token,
                  "phone_number_id": self.settings.phone_number_id, "phone_number": phone_number}
        fields["buttons"] = json.dumps(fields["buttons"])
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=self.transport) as client:
                response = await client.post(self.settings.base_url + "/whatsapp/send/interactive-buttons", data=fields)
        except httpx.TimeoutException:
            raise CardError(504, "whatchimp_timeout", "WhatChimp did not respond in time. Send status is unknown; check before retrying.") from None
        except httpx.RequestError:
            raise CardError(502, "whatchimp_connection", "WhatChimp could not be reached. Send status is unknown; check before retrying.") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        self.last_diagnostics = {"http_status": response.status_code, "response": redact_response(data)}
        if response.status_code in (401, 403):
            raise CardError(502, "whatchimp_authentication", "WhatChimp rejected the server credentials.")
        if response.status_code == 429:
            raise CardError(429, "whatchimp_rate_limit", "WhatChimp is rate limiting requests. Check send status before retrying.")
        if not response.is_success or not isinstance(data, dict) or type(data.get("status")) not in (str, int) or str(data.get("status")) != "1":
            raise CardError(502, "whatchimp_rejected", "WhatChimp did not acknowledge the product card.")
        return self.last_diagnostics
