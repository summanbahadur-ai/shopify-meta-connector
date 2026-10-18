"""Shopify 2026-07 GraphQL documents for filtered order lookup."""

ORDER_LOOKUP = """
query OrderLookup($first: Int!, $after: String, $query: String!, $includePhone: Boolean!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
    nodes { id name email phone @include(if: $includePhone) }
    pageInfo { hasNextPage endCursor }
  }
}
"""

ORDER_STATUS_DETAILS = """
query OrderStatusDetails($id: ID!, $includePhone: Boolean!) {
  order(id: $id) {
    id name email phone @include(if: $includePhone)
    cancelledAt displayFinancialStatus displayFulfillmentStatus
    lineItems(first: 100) {
      nodes { id title quantity currentQuantity requiresShipping }
      pageInfo { hasNextPage endCursor }
    }
    fulfillments {
      id status displayStatus requiresShipping deliveredAt inTransitAt
      trackingInfo { company number url }
      fulfillmentLineItems(first: 100) {
        nodes { quantity lineItem { id title } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

ORDER_ITEMS = """
query OrderItems($id: ID!, $after: String) {
  order(id: $id) {
    lineItems(first: 100, after: $after) {
      nodes { id title quantity currentQuantity requiresShipping }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

FULFILLMENT_ITEMS = """
query FulfillmentItems($id: ID!, $after: String) {
  fulfillment(id: $id) {
    fulfillmentLineItems(first: 100, after: $after) {
      nodes { quantity lineItem { id title } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
