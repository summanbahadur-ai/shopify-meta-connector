from pydantic import BaseModel, Field


class BrowsingError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


class BrowsingErrorResponse(BaseModel):
    success: bool = False
    code: str
    message: str


class MenuCollection(BaseModel):
    id: str
    title: str
    url: str | None = None
    tags: list[str] = Field(default_factory=list)


class CollectionNavigation(BaseModel):
    id: str
    title: str


class MenuCollections(BaseModel):
    menu_id: str
    menu_title: str
    total: int
    collections: list[MenuCollection | CollectionNavigation]
    page: int = 1
    has_next: bool = False


class ProductSummary(BaseModel):
    id: str
    title: str
    handle: str
    image_url: str | None = None
    image_alt: str | None = None
    description: str
    price: str
    currency: str
    compare_at_price: str | None = None
    on_sale: bool = False
    product_url: str


class Pagination(BaseModel):
    has_next_page: bool
    next_cursor: str | None = None


class CollectionProducts(BaseModel):
    collection_id: str
    collection_title: str
    products: list[ProductSummary]
    pagination: Pagination


class SelectedOption(BaseModel):
    name: str
    value: str


class ProductVariant(BaseModel):
    id: str
    title: str
    price: str
    compare_at_price: str | None = None
    available: bool
    selected_options: list[SelectedOption]


class ProductDetails(ProductSummary):
    vendor: str
    product_type: str
    available: bool
    variants: list[ProductVariant]
    whatsapp_message: str
