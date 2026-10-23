from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.product_browsing import canonical_id
from app.schemas.product_browsing import Pagination


class ProductCarouselRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number: Annotated[str, Field(pattern=r"^[1-9][0-9]{7,14}$", max_length=15)]
    collection_id: Annotated[str, Field(max_length=100)]
    limit: Annotated[int, Field(ge=2, le=10, strict=True)] = 4
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    dry_run: Annotated[bool, Field(strict=True)] = False

    @field_validator("collection_id")
    @classmethod
    def valid_collection(cls, value):
        try:
            return canonical_id(value, "Collection")
        except RuntimeError:
            raise ValueError("Provide a valid Shopify collection ID") from None


class CarouselButton(BaseModel):
    id: Annotated[str, Field(max_length=256)]
    title: Annotated[str, Field(max_length=20)]


class CarouselCard(BaseModel):
    product_id: str
    variant_id: str
    title: str
    price: str
    currency: str
    media_url: str
    body: Annotated[str, Field(max_length=160)]
    buttons: Annotated[list[CarouselButton], Field(min_length=1, max_length=2)]


class ProductCarouselPreview(BaseModel):
    status: Literal["prepared"] = "prepared"
    submitted: Literal[False] = False
    collection_id: str
    count: int
    cards: Annotated[list[CarouselCard], Field(min_length=2, max_length=10)]
    pagination: Pagination
