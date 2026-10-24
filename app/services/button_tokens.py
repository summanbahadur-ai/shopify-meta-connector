import json
from pydantic import ValidationError
from app.core.config import ButtonWebhookSettings, ConfigurationError
from app.schemas.button_webhook import ButtonTokenPayload, ButtonWebhookError


def _cipher(settings):
    from cryptography.fernet import Fernet, MultiFernet
    try:
        keys = (settings.token_key, *settings.previous_keys)
        if len(keys) > 6:
            raise ValueError()
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, UnicodeError):
        raise ConfigurationError("Button token encryption is not configured") from None


def generate_button_token(product_id: str, action: str, *, settings=None) -> str:
    settings = settings or ButtonWebhookSettings.from_source()
    try:
        payload = ButtonTokenPayload(action=action, product_id=product_id)
    except ValidationError:
        raise ValueError("Invalid product ID or button action") from None
    return _cipher(settings).encrypt(payload.model_dump_json().encode()).decode("ascii")


def decode_button_token(token: str, *, settings=None) -> ButtonTokenPayload:
    from cryptography.fernet import InvalidToken
    settings = settings or ButtonWebhookSettings.from_source()
    cipher = _cipher(settings)
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 2048:
            raise ValueError()
        raw = cipher.decrypt(token.encode("ascii"))  # Reusable manual buttons: no arbitrary short TTL.
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"version", "action", "product_id"}:
            raise ValueError()
        return ButtonTokenPayload.model_validate(data)
    except (InvalidToken, UnicodeError, ValueError, ValidationError):
        raise ButtonWebhookError(401, "invalid_button_token", "Invalid or missing button token.") from None
