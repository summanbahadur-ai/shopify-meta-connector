import httpx
from uuid import uuid4
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
        fields = {"to": "+" + phone_number.lstrip("+"), "text": card["message"]}
        if card.get("media_url"):
            fields["media"] = {"url": card["media_url"]}
        return await self._send_message(fields)

    async def _send_message(self, fields):
        if self.settings.from_channel:
            fields["from"] = self.settings.from_channel
        headers = {"Authorization": "Bearer " + self.settings.api_key,
                   "Idempotency-Key": str(uuid4())}
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=self.transport) as client:
                response = await client.post(self.settings.base_url + "/messages", json=fields, headers=headers)
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
        error = data.get("error") if isinstance(data, dict) else None
        errors = {
            "window_closed": (409, "The customer-service messaging window is closed."),
            "no_conversation": (409, "No customer conversation is available for this message."),
            "contact_blocked": (409, "Messages cannot be sent to this contact."),
            "channel_not_connected": (409, "The sending channel is not connected."),
            "from_required": (422, "Configure a WhatChimp sending channel for this message."),
        }
        if not response.is_success and isinstance(error, str) and error in errors:
            status, message = errors[error]
            raise CardError(status, "whatchimp_" + error, message)
        if not response.is_success or not isinstance(data, dict) or data.get("status") != "accepted" or not isinstance(data.get("id"), str) or not data["id"].startswith("msg_"):
            raise CardError(502, "whatchimp_rejected", "WhatChimp did not acknowledge the message.")
        return self.last_diagnostics
