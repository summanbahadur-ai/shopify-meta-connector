class ShopifyError(RuntimeError):
    """Base error raised when Shopify cannot satisfy a request."""


class ShopifyAuthenticationError(ShopifyError):
    pass


class ShopifyAPIError(ShopifyError):
    pass


class AmbiguousOrderError(ShopifyError):
    pass


class OrderLookupLimitError(ShopifyError):
    pass
