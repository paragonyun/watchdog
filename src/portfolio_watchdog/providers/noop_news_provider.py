from typing import List

from ..models import NewsItem
from .news_provider import NewsProvider


class NoopNewsProvider(NewsProvider):
    def get_market_summary(self) -> List[NewsItem]:
        return []
