"""Optional verified metafield source only; not added to normal product queries."""
PRODUCT_REVIEWS_QUERY = """
query ButtonProductReviews($productId: ID!, $namespace: String!, $ratingKey: String!, $countKey: String!) {
  product(id: $productId) {
    badge: metafield(namespace: "judgeme", key: "badge") { type value }
    rating: metafield(namespace: $namespace, key: $ratingKey) { type value }
    count: metafield(namespace: $namespace, key: $countKey) { type value }
  }
}
"""
