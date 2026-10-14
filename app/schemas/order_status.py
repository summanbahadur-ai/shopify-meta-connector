"""Validated lookup inputs and the public, customer-data-free response."""

import re

from pydantic import BaseModel, ConfigDict, field_validator


class OrderLookup(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_number: str

    @field_validator("order_number", mode="before")
    @classmethod
    def clean_input(cls, value):
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Lookup values must be text without control characters")
        value = value.strip()
        if not value:
            raise ValueError("Provided lookup values must not be blank")
        return value

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
    message: str
    order_number: str
    status: str
    items: list[OrderItem]
    remaining_items: list[OrderItem]
    shipments: list[Shipment]
