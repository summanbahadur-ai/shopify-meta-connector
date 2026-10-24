from dataclasses import dataclass
from decimal import Decimal
import json
from html.parser import HTMLParser
from app.clients.product_review_queries import PRODUCT_REVIEWS_QUERY


@dataclass(frozen=True)
class VerifiedReviews:
    rating: Decimal
    scale: Decimal
    count: int


class _BadgeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.matches = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "jdgm-prev-badge" in values.get("class", "").split():
            self.matches.append((values.get("data-average-rating"), values.get("data-number-of-reviews")))


class ProductReviewService:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    async def get(self, product_id):
        if not self.settings.reviews_verified:
            return None
        try:
            result = await self.client.query(PRODUCT_REVIEWS_QUERY, {
                "productId": product_id, "namespace": self.settings.reviews_namespace,
                "ratingKey": self.settings.rating_key, "countKey": self.settings.review_count_key})
            product = result.get("product") or {}
            if self.settings.review_source == "judgeme_badge":
                badge = product.get("badge") or {}
                parser = _BadgeParser()
                value = badge.get("value", "")
                if not isinstance(value, str) or len(value) > 100000:
                    return None
                parser.feed(value)
                if len(parser.matches) != 1:
                    return None
                score, count = parser.matches[0]
                rating, total = Decimal(score), int(count)
                if not rating.is_finite() or not 0 <= rating <= 5 or total <= 0:
                    return None
                return VerifiedReviews(rating, Decimal(5), total)
            if self.settings.review_source != "standard":
                return None
            rating, count = product.get("rating") or {}, product.get("count") or {}
            if rating.get("type") != "rating" or count.get("type") != "number_integer":
                return None
            raw = json.loads(rating["value"])
            value, scale, minimum = Decimal(raw["value"]), Decimal(raw["scale_max"]), Decimal(raw["scale_min"])
            total = int(count["value"])
            if not all(v.is_finite() for v in (value, scale, minimum)) or not 0 <= minimum <= value <= scale or scale <= 0 or total <= 0:
                return None
            return VerifiedReviews(value, scale, total)
        except Exception:
            # Optional verified-source reviews never block current price/description.
            return None
