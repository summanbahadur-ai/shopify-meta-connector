"""Admin GraphQL 2026-07 documents. No caller-controlled query fragments."""

PRODUCT_MENU_ID = "gid://shopify/Menu/235088314461"

MENU_QUERY = """
query GetNavigationMenu($menuId: ID!) {
  menu(id: $menuId) {
    id title handle
    items {
      id title type resourceId url tags
      items {
        id title type resourceId url tags
        items { id title type resourceId url tags }
      }
    }
  }
}
"""

PRODUCT_FIELDS = """
  id title handle status tags onlineStoreUrl description descriptionHtml
  featuredMedia { ... on MediaImage { image { url altText } } }
  priceRangeV2 {
    minVariantPrice { amount currencyCode }
    maxVariantPrice { amount currencyCode }
  }
"""
VARIANT_FIELDS = """
  id title price compareAtPrice availableForSale
  selectedOptions { name value }
"""

COLLECTION_PRODUCTS_QUERY = """
query GetCollectionProducts($collectionId: ID!, $first: Int!, $after: String) {
  collection(id: $collectionId) {
    id title
    products(first: $first, after: $after) {
      edges { cursor node {
""" + PRODUCT_FIELDS + """
        variants(first: 50) {
          nodes { price compareAtPrice availableForSale }
          pageInfo { hasNextPage endCursor }
        }
      } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

PRODUCT_DETAILS_QUERY = """
query GetProductDetails($productId: ID!) {
  product(id: $productId) {
""" + PRODUCT_FIELDS + """
    vendor productType
    variants(first: 50) {
      nodes { """ + VARIANT_FIELDS + """ }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

VARIANTS_QUERY = """
query GetProductVariants($productId: ID!, $after: String!) {
  product(id: $productId) {
    variants(first: 50, after: $after) {
      nodes { """ + VARIANT_FIELDS + """ }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

MEMBERSHIP_QUERY = """
query ProductInCollection($productId: ID!, $collectionId: ID!) {
  product(id: $productId) { inCollection(id: $collectionId) }
}
"""

PRODUCT_COLLECTIONS_QUERY = """
query ProductMenuMembership($productId: ID!, $after: String) {
  product(id: $productId) {
    collections(first: 50, after: $after) {
      nodes { id }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
