import json
import logging
from typing import Any, Dict, List, Sequence

import requests

from .config import AssetConfig
from .models import NewsItem
from .providers.news_provider import NewsProvider

logger = logging.getLogger(__name__)
_ALLOWED_IMPACTS = {"긍정", "부정", "중립"}


class OpenAiNewsAnalyzer:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1", timeout_seconds: int = 30) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def analyze(self, items: Sequence[NewsItem], assets: Sequence[AssetConfig]) -> List[NewsItem]:
        if not items:
            return []
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=self._build_payload(items, assets),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content = str(response.json()["choices"][0]["message"]["content"])
        return _apply_analysis_result(items, assets, content)

    def _build_payload(self, items: Sequence[NewsItem], assets: Sequence[AssetConfig]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "너는 개인 포트폴리오 뉴스 분석가다. 매수/매도 조언 없이 영향만 한국어로 짧게 분석하고 JSON만 반환한다."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "portfolio_assets": [{"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "target_weight_percent": round(asset.target_weight * 100, 2)} for asset in assets],
                            "candidate_news": [{"id": index, "title": item.title, "summary": item.summary[:700], "url": item.url, "keyword_related_assets": item.related_assets, "keyword_impact": item.impact, "keyword_reason": item.reason} for index, item in enumerate(items, start=1)],
                            "output_schema": {"items": [{"id": 1, "priority": 5, "impact": "부정|긍정|중립", "related_assets": ["BTC"], "reason": "한국어 1~2문장"}]},
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }


class LlmNewsProvider(NewsProvider):
    def __init__(self, base_provider: NewsProvider, analyzer: OpenAiNewsAnalyzer, assets: Sequence[AssetConfig]) -> None:
        self.base_provider = base_provider
        self.analyzer = analyzer
        self.assets = assets

    def get_market_summary(self) -> List[NewsItem]:
        items = self.base_provider.get_market_summary()
        try:
            return self.analyzer.analyze(items, self.assets) or items
        except Exception as exc:
            logger.warning("LLM news analysis failed, using keyword analysis: %s", exc)
            return items


def _apply_analysis_result(items: Sequence[NewsItem], assets: Sequence[AssetConfig], content: str) -> List[NewsItem]:
    parsed = json.loads(content.strip().strip("`").removeprefix("json").strip())
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("LLM response did not include an items list.")
    allowed_symbols = {asset.symbol for asset in assets}
    by_id = {index: item for index, item in enumerate(items, start=1)}
    analyzed = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = _as_int(raw.get("id"))
        original = by_id.get(item_id)
        if original is None:
            continue
        impact = str(raw.get("impact") or original.impact).strip()
        if impact not in _ALLOWED_IMPACTS:
            impact = original.impact
        related_assets = _clean_related_assets(raw.get("related_assets"), allowed_symbols, original.related_assets)
        reason = str(raw.get("reason") or original.reason).strip()[:260]
        priority = max(1, min(_as_int(raw.get("priority"), 1), 5))
        analyzed.append((priority, item_id, NewsItem(title=original.title, summary=original.summary, source=original.source, url=original.url, published_at=original.published_at, related_assets=related_assets, impact=impact, reason=reason)))
    analyzed.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [item for _, _, item in analyzed]


def _clean_related_assets(value: Any, allowed_symbols: set[str], fallback: Sequence[str]) -> List[str]:
    if not isinstance(value, list):
        return list(fallback)
    cleaned: List[str] = []
    for item in value:
        symbol = str(item).upper().strip()
        if symbol in allowed_symbols and symbol not in cleaned:
            cleaned.append(symbol)
    return cleaned


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
