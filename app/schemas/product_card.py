from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.product_browsing import canonical_id


class ProductCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number: Annotated[str, Field(pattern=r"^[1-9][0-9]{7,14}$", max_length=15)]
    product_id: Annotated[str, Field(max_length=100)]

    @field_validator("product_id")
    @classmethod
    def valid_product(cls, value):
        try:
            return canonical_id(value, "Product")
        except RuntimeError:
            raise ValueError("Provide a valid Shopify product ID") from None


class CardError(RuntimeError):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


class CardProduct(BaseModel):
    id: str
    variant_id: str
    title: str
    price: str
    currency: str
    on_sale: bool
    product_url: str


class ProductCardResponse(BaseModel):
    success: bool = True
    message: str = "Product card submitted to WhatChimp"
    phone_number: str
    product: CardProduct


class ProductCardErrorResponse(BaseModel):
    success: bool = False
    code: str
    message: str
