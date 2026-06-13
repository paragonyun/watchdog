import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

from ..config import AssetConfig
from ..models import NewsItem
from ..news_analysis import analyze_news_items, default_news_queries
from .news_provider import NewsProvider

logger = logging.getLogger(__name__)


class RssNewsProvider(NewsProvider):
    def __init__(self, assets: List[AssetConfig], queries: Optional[List[str]] = None, lookback_hours: int = 24, max_items: int = 5, max_items_per_query: int = 5, timeout_seconds: int = 10) -> None:
        self.assets = assets
        self.queries = queries or default_news_queries()
        self.lookback_hours = lookback_hours
        self.max_items = max_items
        self.max_items_per_query = max_items_per_query
        self.timeout_seconds = timeout_seconds
        self.failed_query_count = 0

    @property
    def all_queries_failed(self) -> bool:
        return bool(self.queries) and self.failed_query_count == len(self.queries)

    def get_market_summary(self) -> List[NewsItem]:
        self.failed_query_count = 0
        raw_items: List[NewsItem] = []
        for query in self.queries:
            raw_items.extend(self._fetch_query(query))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        recent = [item for item in self._dedupe(raw_items) if item.published_at is None or item.published_at.astimezone(timezone.utc) >= cutoff]
        analyzed = analyze_news_items(recent, self.assets)
        analyzed.sort(key=_sort_key, reverse=True)
        return analyzed[: self.max_items]

    def _fetch_query(self, query: str) -> List[NewsItem]:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            response = requests.get(url, timeout=self.timeout_seconds, headers={"User-Agent": "PortfolioWatchdog/1.0"})
            response.raise_for_status()
            return self._parse_rss(response.content)[: self.max_items_per_query]
        except Exception as exc:
            self.failed_query_count += 1
            logger.warning("RSS news lookup failed for query %s: %s", query, exc)
            return []

    def _parse_rss(self, content: bytes) -> List[NewsItem]:
        root = ET.fromstring(content)
        items: List[NewsItem] = []
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            source_node = item.find("source")
            source = (source_node.text or "Google News").strip() if source_node is not None else "Google News"
            items.append(
                NewsItem(
                    title=title,
                    summary=(item.findtext("description") or "").strip(),
                    source=source,
                    url=(item.findtext("link") or "").strip(),
                    published_at=_parse_pub_date(item.findtext("pubDate")),
                )
            )
        return items

    def _dedupe(self, items: List[NewsItem]) -> List[NewsItem]:
        result: List[NewsItem] = []
        seen: Dict[str, bool] = {}
        for item in items:
            key = item.url or item.title
            if key in seen:
                continue
            seen[key] = True
            result.append(item)
        return result


def _parse_pub_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _sort_key(item: NewsItem) -> tuple:
    impact_rank = {"부정": 3, "긍정": 2, "중립": 1}
    published = item.published_at or datetime.min.replace(tzinfo=timezone.utc)
    return (impact_rank.get(item.impact, 0), len(item.related_assets), published)
