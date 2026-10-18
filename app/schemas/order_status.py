"""Validated lookup inputs and the public, customer-data-free response."""

import re
from typing import Literal

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_phone(value: str) -> str:
    value = value.strip()
    if len(value) > 64 or not re.fullmatch(r"\+[0-9 () .-]+", value):
        raise ValueError("Phone must include a country code, for example +14155552671")
    try:
        number = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Invalid phone number") from exc
    if not phonenumbers.is_valid_number(number):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def email_forms(value: str) -> tuple[str, ...]:
    """Canonical and Unicode-domain spellings for exact matching and IDN search."""
    if len(value) > 254:
        raise ValueError("Invalid email address")
    try:
        parsed = validate_email(value.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("Invalid email address") from exc
    canonical = f"{parsed.local_part}@{parsed.ascii_domain}".casefold()
    return tuple(dict.fromkeys((canonical, parsed.normalized.casefold())))


class OrderLookup(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_number: str
    email: str
    phone: str | None = None

    @field_validator("order_number", "email", "phone", mode="before")
    @classmethod
    def clean_input(cls, value, info):
        if value is None and info.field_name == "phone":
            return None
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Lookup values must be text without control characters")
        value = value.strip()
        if not value:
            raise ValueError("Provided lookup values must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return email_forms(value)[0]

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @field_validator("order_number")
    @classmethod
    def valid_order_name(cls, value):
        if value is not None:
            if len(value) > 128 or value == "#":
                raise ValueError("Order number must be between 1 and 128 characters")
            if re.fullmatch(r"[0-9]+", value):
                value = f"#{value}"
        return value


class OrderItem(BaseModel):
    title: str
    quantity: int


class TrackingInfo(BaseModel):
    company: str | None = None
    number: str | None = None
    url: str | None = None


class Shipment(BaseModel):
    status: str
    items: list[OrderItem]
    tracking: list[TrackingInfo]


class OrderStatusResponse(BaseModel):
    success: Literal[True] = True
    message: str
    order_number: str
    status: str
    remaining_items: list[OrderItem] = Field(default_factory=list)
    shipments: list[Shipment] = Field(default_factory=list)


class OrderInputIssue(BaseModel):
    field: str
    code: str
    message: str


class OrderLookupErrorResponse(BaseModel):
    success: Literal[False] = False
    code: str
    message: str
    errors: list[OrderInputIssue] = Field(default_factory=list)
