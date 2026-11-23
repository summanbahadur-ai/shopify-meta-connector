from types import SimpleNamespace
import json
import httpx
import pytest
from app.clients.whatchimp_client import WhatChimpClient

async def test_new_message_transport():
    def handle(req):
        assert str(req.url) == "https://api.whatchimp.com/v1/messages"
        assert req.headers["Authorization"] == "Bearer test-key"
        assert req.headers["Idempotency-Key"]
        assert json.loads(req.content) == {"to": "+923001234567", "text": "Details"}
        return httpx.Response(201, json={"id": "msg_test", "status": "accepted"})
    settings = SimpleNamespace(api_key="test-key", from_channel="", base_url="https://api.whatchimp.com/v1")
    await WhatChimpClient(settings, httpx.MockTransport(handle)).send_card("923001234567", {"message": "Details"})


@pytest.mark.parametrize("error,expected_status", [("window_closed", 409), ("no_conversation", 409), ("contact_blocked", 409), ("channel_not_connected", 409), ("from_required", 422), ({"message": "private"}, 502)])
async def test_new_errors_are_curated(error, expected_status):
    from app.schemas.product_card import CardError
    settings = SimpleNamespace(api_key="test-key", from_channel="", base_url="https://api.whatchimp.com/v1")
    client = WhatChimpClient(settings, httpx.MockTransport(lambda req: httpx.Response(409 if expected_status != 422 else 422, json={"error": error, "message": "private"})))
    with pytest.raises(CardError) as exc:
        await client.send_card("923001234567", {"message": "Details"})
    assert exc.value.status == expected_status
    assert "private" not in str(exc.value) + repr(client.last_diagnostics)


async def test_explicit_sender_and_unique_send_keys():
    keys = []
    def handle(req):
        assert json.loads(req.content)["from"] == "ch_test"
        keys.append(req.headers["Idempotency-Key"])
        return httpx.Response(201, json={"id": "msg_test", "status": "accepted"})
    settings = SimpleNamespace(api_key="test-key", from_channel="ch_test", base_url="https://api.whatchimp.com/v1")
    client = WhatChimpClient(settings, httpx.MockTransport(handle))
    for _ in range(2):
        await client.send_card("923001234567", {"message": "Details"})
    assert len(set(keys)) == 2


def test_settings_require_new_key_and_reject_old_base(monkeypatch):
    from app.core.config import ConfigurationError, WhatChimpSettings
    monkeypatch.setenv("WHATCHIMP_API_KEY", "")
    monkeypatch.setenv("WHATCHIMP_API_TOKEN_2", "old-token")
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "inbound")
    with pytest.raises(ConfigurationError):
        WhatChimpSettings.from_request(SimpleNamespace(scope={}))
    monkeypatch.setenv("WHATCHIMP_API_KEY", "new-key")
    monkeypatch.setenv("WHATCHIMP_API_BASE_URL", "https://app.whatchimp.com/api/v1")
    with pytest.raises(ConfigurationError):
        WhatChimpSettings.from_request(SimpleNamespace(scope={}))
