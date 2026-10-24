import re
from dataclasses import dataclass
from app.schemas.order_status import normalize_phone


@dataclass(frozen=True, repr=False)
class CustomerIdentity:
    phone: str | None = None
    subscriber_id: str | None = None
    event_id: str | None = None


def field_at(data, path):
    if not path or len(path) > 256:
        return None
    pieces = path.split(".")
    if len(pieces) > 10:
        return None
    for part in pieces:
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isascii() and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


def identify_customer(body, query, settings):
    source = {"body": body, "query": query}
    paths = [settings.phone_path] if settings.phone_path else [
        prefix + name for prefix in ("body.", "body.data.", "body.payload.", "query.")
        for name in ("phone_number", "wa_id", "from", "contact.phone", "contact.wa_id", "subscriber.phone_number", "subscriber.wa_id")]
    phones = set()
    for path in paths:
        raw = field_at(source, path)
        if isinstance(raw, str) and len(raw) <= 64:
            try:
                phones.add(normalize_phone(raw if raw.startswith("+") else "+" + raw).lstrip("+"))
            except ValueError:
                pass
    # Never choose between conflicting recipients or use the merchant phone_number_id.
    phone = next(iter(phones)) if len(phones) == 1 else None
    def identifier(paths):
        values = {value for path in paths if isinstance(value := field_at(source, path), str)
                  and re.fullmatch(r"[A-Za-z0-9_.:\-]{1,200}", value)}
        return next(iter(values)) if len(values) == 1 else None
    subscriber = identifier([settings.subscriber_path] if settings.subscriber_path else
                            ["body.subscriber_id", "body.subscriber.id", "query.subscriber_id"])
    event = identifier([settings.event_id_path] if settings.event_id_path else
                      ["body.event_id", "body.message_id", "body.message.id", "query.event_id", "query.message_id"])
    return CustomerIdentity(phone, subscriber, event)
