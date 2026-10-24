import pytest
from cryptography.fernet import Fernet
from app.services.button_tokens import generate_button_token, decode_button_token


@pytest.fixture
def key(monkeypatch):
    value = Fernet.generate_key().decode()
    monkeypatch.setenv("WHATCHIMP_BUTTON_TOKEN_KEY", value)
    return value


def test_token_round_trip(key):
    token = generate_button_token("8173166231645", "view_details")
    assert "8173166231645" not in token
    payload = decode_button_token(token)
    assert payload.model_dump() == {"version": 1, "action": "view_details", "product_id": "8173166231645"}


from app.messaging.button_details_formatter import format_button_details
from app.schemas.product_browsing import ProductDetails


def details(**changes):
    data = dict(id="gid://shopify/Product/123", variant_id="gid://shopify/ProductVariant/456",
        title="Face Wash", handle="face-wash", description="<p>Live description.</p>",
        price="1650.00", currency="PKR", compare_at_price="1940.00", on_sale=True,
        product_url="https://example.com/face-wash", vendor="Dr Elements", product_type="Wash",
        available=True, variants=[], whatsapp_message="")
    data.update(changes)
    return ProductDetails(**data)


def test_details_text_sale_and_no_fabricated_reviews():
    text = format_button_details(details())
    assert "PKR 1,650" in text and "PKR 1,940" in text
    assert "14.95% OFF" in text
    assert "Live description." in text and "<p>" not in text
    assert "Rating" not in text


from fastapi.testclient import TestClient
from app.main import app




import json
import logging
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs
import httpx
from app.core.config import ButtonWebhookSettings, WhatChimpSettings
from app.schemas.button_webhook import ButtonWebhookError
from app.services.button_identity import CustomerIdentity, identify_customer
from app.services.button_webhook import ButtonDetailsService
from app.services.button_state import D1ButtonState, local_state
from app.services.product_reviews import ProductReviewService, VerifiedReviews
from app.clients.whatchimp_text_client import WhatChimpTextClient
from app.api import button_webhook as route


@pytest.fixture(autouse=True)
def safe_defaults(monkeypatch):
    for name in ("WHATCHIMP_BUTTON_TOKEN_PREVIOUS_KEYS", "WHATCHIMP_BUTTON_PHONE_PATH", "WHATCHIMP_BUTTON_EVENT_ID_PATH", "WHATCHIMP_BUTTON_SUBSCRIBER_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WHATCHIMP_BUTTON_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("WHATCHIMP_BUTTON_WEBHOOK_DIAGNOSTIC_MODE", "true")
    monkeypatch.setenv("WHATCHIMP_BUTTON_PAYLOAD_VERIFIED", "false")
    local_state.windows.clear()
    local_state.claims.clear()
    monkeypatch.setattr(route, "get_shopify_service", lambda request: SimpleNamespace(client=None))
    monkeypatch.setattr(route, "ProductBrowsingService", lambda client: SimpleNamespace(product_details=AsyncMock(return_value=details())))
    monkeypatch.setattr(route, "WhatChimpTextClient", lambda config: SimpleNamespace(send_text=AsyncMock()))
    monkeypatch.setattr(route.WhatChimpSettings, "from_request", lambda request: WhatChimpSettings("test-token", "123", "test-key"))


def settings(key, **changes):
    return replace(ButtonWebhookSettings(token_key=key), **changes)


@pytest.mark.parametrize("product_id", ["123", "gid://shopify/Product/123"])
def test_numeric_and_gid_tokens(key, product_id):
    assert decode_button_token(generate_button_token(product_id, "view_details")).product_id == "123"


@pytest.mark.parametrize("product_id", ["0", "-1", "abc", "gid://shopify/Collection/1", "1:2", "1\n"])
def test_bad_product(key, product_id):
    with pytest.raises(ValueError):
        generate_button_token(product_id, "view_details")


@pytest.mark.parametrize("data", ["not-json", {"version": 2, "action": "view_details", "product_id": "1"},
    {"version": 1, "action": "add", "product_id": "1"},
    {"version": True, "action": "view_details", "product_id": "1"},
    {"version": 1, "action": "view_details", "product_id": "bad"},
    {"action": "view_details", "product_id": "1"},
    {"version": 1, "action": "view_details", "product_id": "1", "phone": "923001234567"}])
def test_invalid_decrypted_payload(key, data):
    raw = data if isinstance(data, str) else json.dumps(data)
    token = Fernet(key.encode()).encrypt(raw.encode()).decode()
    with pytest.raises(ButtonWebhookError):
        decode_button_token(token)


def test_tampered_wrong_key_and_rotation(key):
    token = generate_button_token("1", "view_details")
    with pytest.raises(ButtonWebhookError):
        decode_button_token(token[:-5] + "AAAAA")
    other = Fernet.generate_key().decode()
    with pytest.raises(ButtonWebhookError):
        decode_button_token(token, settings=settings(other))
    assert decode_button_token(token, settings=settings(other, previous_keys=(key,))).product_id == "1"
    old = Fernet(key.encode()).encrypt_at_time(b'{"version":1,"action":"view_details","product_id":"1"}', 1000000000).decode()
    assert decode_button_token(old).product_id == "1"


@pytest.mark.parametrize("method", ["get", "post"])
def test_plain_button_sends_without_token_key_flags_or_api_key(monkeypatch, method):
    # Old disable/diagnostic settings must no longer block a valid request.
    monkeypatch.setenv("WHATCHIMP_BUTTON_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("WHATCHIMP_BUTTON_WEBHOOK_DIAGNOSTIC_MODE", "true")
    monkeypatch.setenv("WHATCHIMP_API_TOKEN", "test-token")
    monkeypatch.setenv("WHATCHIMP_PHONE_NUMBER_ID", "12345")
    source = SimpleNamespace(product_details=AsyncMock(return_value=details()))
    sender = SimpleNamespace(send_text=AsyncMock(), send_card=AsyncMock())
    monkeypatch.setattr(route, "get_shopify_service", lambda request: SimpleNamespace(client=None))
    monkeypatch.setattr(route, "ProductBrowsingService", lambda client: source)
    monkeypatch.setattr(route, "WhatChimpTextClient", lambda config: sender)
    monkeypatch.delenv("WHATCHIMP_BUTTON_TOKEN_KEY", raising=False)
    client = TestClient(app)
    if method == "post":
        result = client.post("/api/whatsapp/button-click", params={"product_id": "123", "action": "view_details"}, json={"chat_id": "923244374905", "whatsapp_bot_username": "+92 309 8880105"})
    else:
        result = client.get("/api/whatsapp/button-click", params={"product_id": "123", "action": "view_details", "chat_id": "923244374905"})
    assert result.status_code == 200 and result.json()["mode"] == "submitted"
    sender.send_text.assert_awaited_once()
    sender.send_card.assert_not_awaited()
    assert client.post("/api/whatsapp/button-click").status_code == 422
    assert client.get("/api/whatsapp/button-click?token=bad").status_code == 422


def test_customer_mapping_is_explicit_and_not_invented(key, monkeypatch):
    data = {"customer": {"whatsapp": "923244374905"}, "subscriber": "sub123", "event": "unique-event"}
    assert identify_customer(data, {}, settings(key)).phone is None
    config = settings(key, phone_path="body.customer.whatsapp", subscriber_path="body.subscriber", event_id_path="body.event")
    identity = identify_customer(data, {}, config)
    assert identity.phone == "923244374905" and identity.subscriber_id == "sub123" and identity.event_id == "unique-event"
    assert identify_customer({"customer": {"whatsapp": "03244374905"}}, {}, config).phone is None


def test_product_action_required_and_other_routes_protected(key, monkeypatch):
    client = TestClient(app)
    assert client.get("/api/whatsapp/button-click").status_code == 422
    monkeypatch.setenv("WHATCHIMP_INBOUND_API_KEY", "expected")
    monkeypatch.setenv("PRODUCT_BROWSING_API_KEY", "expected")
    assert client.post("/api/whatsapp/product-card", json={"phone_number":"923001234567", "collection_id":"1"}).status_code == 401
    assert client.get("/api/v1/shopify/products/collections").status_code == 401
    assert client.post("/api/whatsapp/incoming").status_code == 404


def test_sensitive_data_not_logged(key, monkeypatch, caplog):
    monkeypatch.setattr(route, "get_button_service", route.get_button_service)
    caplog.set_level(logging.INFO)
    token = generate_button_token("1", "view_details")
    result = TestClient(app).post("/api/whatsapp/button-click", params={"product_id": "1", "action": "view_details", "token": token}, json={"chat_id": "923244374905", "apiToken": "private-token", "text":"private customer text"})
    assert result.status_code in (200, 422)
    for value in (token, key, "923244374905", "private-token", "private customer text"):
        assert value not in caplog.text + result.text


def test_rate_limit_and_size(key, monkeypatch):
    monkeypatch.setenv("WHATCHIMP_BUTTON_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("WHATCHIMP_BUTTON_RATE_LIMIT", "1")
    client = TestClient(app)
    url = "/api/whatsapp/button-click?product_id=1&action=view_details&chat_id=923244374905"
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 429
    local_state.windows.clear()
    assert client.post(url, json={"text": "x" * 65536}).status_code == 413




def live_service(key, **changes):
    config = settings(key, phone_path="body.verified_phone", **changes)
    source = SimpleNamespace(product_details=AsyncMock(return_value=details()))
    sender = SimpleNamespace(send_text=AsyncMock(), send_card=AsyncMock())
    state = SimpleNamespace(durable=True, claim=AsyncMock(return_value=True))
    reviews = SimpleNamespace(get=AsyncMock(return_value=None))
    return ButtonDetailsService(source, sender, reviews, state, config)


async def test_live_details_only_never_image_card(key):
    service = live_service(key)
    result = await service.handle(decode_button_token(generate_button_token("123", "view_details")), CustomerIdentity(phone="923244374905", event_id="event123"))
    service.browsing.product_details.assert_awaited_once_with("123")
    service.sender.send_card.assert_not_awaited()
    service.sender.send_text.assert_awaited_once()
    assert "Live description." in service.sender.send_text.call_args.args[1]
    assert result["mode"] == "submitted" and result["submitted"] is True


async def test_missing_customer_duplicate_and_durable_state_gate(key):
    service = live_service(key)
    payload = decode_button_token(generate_button_token("123", "view_details"))
    with pytest.raises(ButtonWebhookError) as exc:
        await service.handle(payload, CustomerIdentity(subscriber_id="123"))
    assert exc.value.code == "customer_not_identified"
    service.state.claim.return_value = False
    result = await service.handle(payload, CustomerIdentity(phone="923244374905"))
    assert result["mode"] == "duplicate" and result["submitted"] is False
    service.sender.send_text.assert_not_awaited()


async def test_state_ttl_for_event_and_repeated_click(key):
    service = live_service(key)
    payload = decode_button_token(generate_button_token("123", "view_details"))
    await service.handle(payload, CustomerIdentity(phone="923244374905", event_id="event123"))
    assert service.state.claim.call_args.args[1] == 86400
    await service.handle(payload, CustomerIdentity(phone="923244374905"))
    assert service.state.claim.call_args.args[1] == 10


@pytest.mark.parametrize("compare", [None, "1650.00", "1000.00"])
def test_no_sale(compare):
    text = format_button_details(details(compare_at_price=compare, on_sale=False))
    assert "Special Offer" not in text and "Original Price" not in text


def test_selected_variant_pair_and_verified_reviews():
    product = details(price="1000.00", compare_at_price="1250.00", variants=[
        {"id":"gid://shopify/ProductVariant/456", "title":"Default", "price":"1000.00", "compare_at_price":"1250.00", "available":True, "selected_options":[]},
        {"id":"gid://shopify/ProductVariant/789", "title":"Other", "price":"5000.00", "compare_at_price":"9000.00", "available":True, "selected_options":[]}])
    text = format_button_details(product, VerifiedReviews(Decimal("4.7"), Decimal("5"), 28))
    assert "20% OFF" in text and "9,000" not in text
    assert "4.7/5 (28 reviews)" in text
    assert len(format_button_details(details(description="x" * 10000))) <= 4000


async def test_reviews_unverified_missing_valid_and_failure(key):
    client = SimpleNamespace(query=AsyncMock())
    service = ProductReviewService(client, settings(key))
    assert await service.get("gid://shopify/Product/123") is None
    client.query.assert_not_awaited()
    service.settings = settings(key, reviews_verified=True)
    client.query.return_value = {"product": {"rating":{"type":"rating", "value":'{"value":"4.7","scale_max":"5","scale_min":"1"}'}, "count":{"type":"number_integer", "value":"28"}}}
    assert (await service.get("gid://shopify/Product/123")).count == 28
    client.query.return_value = {"product": {}}
    assert await service.get("gid://shopify/Product/123") is None
    client.query.side_effect = RuntimeError("private-token")
    assert await service.get("gid://shopify/Product/123") is None


async def test_text_wire_payload_and_acknowledgement():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path == "/api/v1/whatsapp/send"
        fields = parse_qs(request.content.decode())
        assert fields["message"] == ["Product details"] and fields["phone_number"] == ["923244374905"]
        assert "buttons" not in fields and "media_url" not in fields
        return httpx.Response(200, json={"status":"1"})
    sender = WhatChimpTextClient(WhatChimpSettings("private", "123", "inbound"), httpx.MockTransport(handler))
    await sender.send_text("923244374905", "Product details")
    assert len(calls) == 1


@pytest.mark.parametrize("code,body,error", [(401,{},"whatchimp_authentication"), (429,{},"whatchimp_rate_limit"),
    (500,{},"whatchimp_rejected"), (200,{"status":"0"},"whatchimp_rejected"), (200,{"status":True},"whatchimp_rejected")])
async def test_text_provider_failure_no_retry(code, body, error):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(code,json=body)
    sender=WhatChimpTextClient(WhatChimpSettings("private","123","inbound"),httpx.MockTransport(handler))
    with pytest.raises(Exception) as exc:
        await sender.send_text("923244374905","Details")
    assert exc.value.code==error and len(calls)==1


async def test_shopify_and_sender_errors_do_not_resend(key):
    service=live_service(key)
    payload=decode_button_token(generate_button_token("123","view_details"))
    service.browsing.product_details.side_effect=RuntimeError("private")
    with pytest.raises(RuntimeError):
        await service.handle(payload,CustomerIdentity(phone="923244374905"))
    service.sender.send_text.assert_not_awaited()
    service.browsing.product_details.side_effect=None
    service.sender.send_text.side_effect=RuntimeError("private")
    with pytest.raises(RuntimeError):
        await service.handle(payload,CustomerIdentity(phone="923244374905"))
    assert service.sender.send_text.await_count==1


async def test_review_service_error_does_not_block_send(key):
    service=live_service(key)
    service.reviews.get.side_effect=RuntimeError("optional review source failed")
    result=await service.handle(decode_button_token(generate_button_token("123","view_details")), CustomerIdentity(phone="923244374905"))
    assert result["submitted"] is True


async def test_atomic_d1_sql_persists_across_service_instances(monkeypatch):
    import sqlite3
    from pathlib import Path
    database=sqlite3.connect(":memory:")
    database.row_factory=sqlite3.Row
    database.executescript(Path("scripts/button_webhook_state.sql").read_text())
    class Statement:
        def __init__(self,sql):
            self.sql=sql
        def bind(self,*args):
            self.args=args
            return self
        async def first(self):
            row=database.execute(self.sql,self.args).fetchone()
            database.commit()
            return dict(row) if row else None
    class Database:
        def prepare(self,sql):
            return Statement(sql)
    first=D1ButtonState(Database())
    second=D1ButtonState(Database())
    now=[1000]
    monkeypatch.setattr("app.services.button_state.time.time",lambda:now[0])
    assert await first.allow("rate",2)
    assert await second.allow("rate",2)
    assert not await first.allow("rate",2)
    assert await first.claim("event",86400)
    assert not await second.claim("event",86400)
    now[0]+=61
    assert await second.allow("rate",2)
    assert not await second.claim("event",86400)
    now[0]+=86400
    assert await second.claim("event",86400)
    database.close()


def test_cli_generates_plain_product_specific_url(monkeypatch):
    import subprocess,sys
    monkeypatch.delenv("WHATCHIMP_BUTTON_TOKEN_KEY", raising=False)
    result=subprocess.run([sys.executable,"scripts/generate_whatchimp_button_url.py","--product-id","123"],capture_output=True,text=True)
    assert result.returncode==0
    assert "/api/whatsapp/button-click?" in result.stdout
    assert parse_qs(result.stdout.strip().split("?",1)[1]) == {"product_id": ["123"], "action": ["view_details"]}




async def test_text_timeout_has_no_retry():
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-token",request=request)
    sender=WhatChimpTextClient(WhatChimpSettings("private","123","inbound"),httpx.MockTransport(handler))
    with pytest.raises(Exception) as exc:
        await sender.send_text("923244374905","Details")
    assert exc.value.code=="whatchimp_timeout" and len(calls)==1


def test_route_shopify_and_provider_errors_are_curated(key,monkeypatch):
    from app.core.exceptions import ShopifyAPIError
    from app.schemas.product_card import CardError
    service=live_service(key)
    service.settings=replace(service.settings,phone_path="body.verified_phone")
    payload=decode_button_token(generate_button_token("123","view_details"))
    app.dependency_overrides[route.get_button_service]=lambda:(service,payload)
    monkeypatch.setenv("WHATCHIMP_BUTTON_PHONE_PATH","body.verified_phone")
    try:
        service.browsing.product_details.side_effect=ShopifyAPIError("private Shopify details")
        response=TestClient(app).post("/api/whatsapp/button-click",json={"verified_phone":"923244374905"})
        assert response.status_code==502 and "private" not in response.text
        service.browsing.product_details.side_effect=None
        service.sender.send_text.side_effect=CardError(502,"whatchimp_rejected","WhatChimp did not acknowledge the text message.")
        response=TestClient(app).post("/api/whatsapp/button-click",json={"verified_phone":"923244374905"})
        assert response.status_code==502 and response.json()["code"]=="whatchimp_rejected"
    finally:
        app.dependency_overrides.pop(route.get_button_service,None)


async def test_verified_judgeme_badge_review_source(key):
    client=SimpleNamespace(query=AsyncMock(return_value={"product":{"badge":{"type":"string","value":"<div class='jdgm-prev-badge' data-average-rating='4.70' data-number-of-reviews='28'></div>"}}}))
    config=replace(settings(key,reviews_verified=True),review_source="judgeme_badge")
    reviews=await ProductReviewService(client,config).get("gid://shopify/Product/123")
    assert reviews.rating==Decimal("4.70") and reviews.count==28 and reviews.scale==5







def test_automatic_customer_phone_and_ambiguity(key):
    assert identify_customer({"phone_number":"923244374905"}, {}, settings(key)).phone == "923244374905"
    assert identify_customer({"contact":{"phone":"+923244374905"}}, {}, settings(key)).phone == "923244374905"
    assert identify_customer({}, {"phone_number":"923244374905"}, settings(key)).phone == "923244374905"
    assert identify_customer({"phone_number":"923244374905"}, {"phone_number":"923001234567"}, settings(key)).phone is None
    assert identify_customer({"phone_number_id":"923244374905"}, {}, settings(key)).phone is None


async def test_local_duplicate_suppression_needs_no_database():
    from app.services.button_state import local_state
    local_state.claims.clear()
    assert await local_state.claim("example",10)
    assert not await local_state.claim("example",10)


@pytest.mark.parametrize("params", [
    {"product_id": "bad", "action": "view_details"},
    {"product_id": "123", "action": "add"},
    {"product_id": "123"},
    {"action": "view_details"},
    [("product_id", "123"), ("product_id", "456"), ("action", "view_details")],
])
def test_plain_query_validation_prevents_external_calls(params, monkeypatch):
    source = SimpleNamespace(product_details=AsyncMock())
    sender = SimpleNamespace(send_text=AsyncMock())
    monkeypatch.setattr(route, "ProductBrowsingService", lambda client: source)
    monkeypatch.setattr(route, "WhatChimpTextClient", lambda config: sender)
    response = TestClient(app).post("/api/whatsapp/button-click", params=params, json={"chat_id": "923244374905"})
    assert response.status_code == 422
    source.product_details.assert_not_awaited()
    sender.send_text.assert_not_awaited()


def test_captured_whatchimp_post_and_retry(monkeypatch):
    monkeypatch.delenv("WHATCHIMP_BUTTON_TOKEN_KEY", raising=False)
    source = SimpleNamespace(product_details=AsyncMock(return_value=details()))
    sender = SimpleNamespace(send_text=AsyncMock())
    monkeypatch.setattr(route, "ProductBrowsingService", lambda client: source)
    monkeypatch.setattr(route, "WhatChimpTextClient", lambda config: sender)
    data = {
        "first_name": "Test Customer", "chat_id": "923244374905",
        "postbackid": "n5wAbf06801VWw6", "user_input_data": [],
        "reply_message_id": "wamid.original-card", "wa_message_id": "wamid.customer-click-1",
        "whatsapp_bot_username": "+92 309 8880105",
    }
    identity = identify_customer(data, {}, ButtonWebhookSettings())
    assert identity.phone == "923244374905"
    assert identity.event_id == "wamid.customer-click-1"
    client = TestClient(app)
    url = "/api/whatsapp/button-click?product_id=8173166231645&action=view_details"
    assert client.post(url, json=data).json()["mode"] == "submitted"
    source.product_details.assert_awaited_once_with("8173166231645")
    assert sender.send_text.call_args.args[0] == "923244374905"
    assert client.post(url, json=data).json()["mode"] == "duplicate"
    sender.send_text.assert_awaited_once()
    data["wa_message_id"] = "wamid.customer-click-2"
    assert client.post(url, json=data).json()["mode"] == "submitted"
    assert sender.send_text.await_count == 2


def test_business_number_and_original_message_are_not_customer_identity():
    identity = identify_customer({"whatsapp_bot_username": "+92 309 8880105",
        "postbackid": "static-button", "reply_message_id": "wamid.original-card"}, {}, ButtonWebhookSettings())
    assert identity.phone is None and identity.event_id is None
    response = TestClient(app).post("/api/whatsapp/button-click?product_id=123&action=view_details",
        json={"whatsapp_bot_username": "+92 309 8880105"})
    assert response.status_code == 422 and response.json()["code"] == "customer_not_identified"


def test_plain_webhook_openapi():
    operation = app.openapi()["paths"]["/api/whatsapp/button-click"]["post"]
    assert not operation.get("security")
    assert {p["name"] for p in operation["parameters"]} == {"product_id", "action"}
