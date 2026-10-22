from typing import Annotated
from pydantic import BaseModel, Field, field_validator
from app.services.product_browsing import canonical_id


class ProductCardRequest(BaseModel):
    phone_number: Annotated[str, Field(pattern=r"^[1-9][0-9]{7,14}$", max_length=15)]
    collection_id: Annotated[str, Field(max_length=100)]
    product_index: Annotated[int, Field(ge=0, strict=True)] = 0

    @field_validator("collection_id")
    @classmethod
    def valid_collection(cls, value):
        try:
            return canonical_id(value, "Collection")
        except RuntimeError:
            raise ValueError("Provide a valid Shopify collection ID") from None


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


class ProductCardResponse(BaseModel):
    success: bool = True
    message: str = "Product card submitted to WhatChimp"
    phone_number: str
    collection_id: str
    product_index: int
    product: CardProduct


class ProductCardErrorResponse(BaseModel):
    success: bool = False
    code: str
    message: str
