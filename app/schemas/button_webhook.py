from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, field_validator


class ButtonWebhookError(RuntimeError):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


class ButtonTokenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1] = 1
    action: Literal["view_details"]
    product_id: str

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Invalid version")
        return value

    @field_validator("product_id")
    @classmethod
    def normalize_product(cls, value):
        prefix = "gid://shopify/Product/"
        numeric = value.removeprefix(prefix)
        if not re.fullmatch(r"[1-9][0-9]{0,19}", numeric):
            raise ValueError("Invalid product ID")
        return numeric
