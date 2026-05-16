import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AssetEvaluation, NewsItem, PortfolioEvaluation


class HistoryRepository:
    def __init__(self, path: str, retention_days: int = 45) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"portfolio_snapshots": [], "news_items": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"portfolio_snapshots": [], "news_items": []}
        if not isinstance(data, dict):
            return {"portfolio_snapshots": [], "news_items": []}
        return {
            "portfolio_snapshots": data.get("portfolio_snapshots", []) or [],
            "news_items": data.get("news_items", []) or [],
        }

    def append_portfolio(self, portfolio: PortfolioEvaluation, captured_at: Optional[datetime] = None) -> None:
        state = self.load()
        state["portfolio_snapshots"].append(_portfolio_snapshot(portfolio, captured_at or datetime.now()))
        self.save(state)

    def append_news(self, items: List[NewsItem], captured_at: Optional[datetime] = None) -> None:
        if not items:
            return
        state = self.load()
        existing_keys = {_news_key(item) for item in state["news_items"]}
        captured = captured_at or datetime.now()
        for item in items:
            snapshot = _news_snapshot(item, captured)
            key = _news_key(snapshot)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            state["news_items"].append(snapshot)
        self.save(state)

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            tmp_path.write_text(json.dumps(self._prune(state), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _prune(self, state: Dict[str, Any]) -> Dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        return {
            "portfolio_snapshots": [
                item
                for item in state.get("portfolio_snapshots", [])
                if (_parse_datetime(item.get("captured_at")) or cutoff) >= cutoff
            ][-500:],
            "news_items": [
                item
                for item in state.get("news_items", [])
                if (_parse_datetime(item.get("captured_at")) or cutoff) >= cutoff
            ][-1000:],
        }


def _portfolio_snapshot(portfolio: PortfolioEvaluation, captured_at: datetime) -> Dict[str, Any]:
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "total_value_krw": round(portfolio.total_value_krw, 2),
        "asset_groups": {
            "coin": round(_sum_by_type(portfolio.assets, "coin"), 2),
            "equity": round(_sum_by_type(portfolio.assets, "equity"), 2),
            "cash": round(_sum_by_type(portfolio.assets, "cash"), 2),
        },
        "assets": [_asset_snapshot(asset) for asset in portfolio.assets],
    }


def _asset_snapshot(asset: AssetEvaluation) -> Dict[str, Any]:
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "value_krw": round(asset.current_value_krw, 2),
        "weight_percent": round(asset.current_weight * 100, 4),
        "profit_loss_rate_percent": asset.profit_loss_rate_pct,
    }


def _news_snapshot(item: NewsItem, captured_at: datetime) -> Dict[str, Any]:
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "published_at": item.published_at.isoformat(timespec="seconds") if item.published_at else None,
        "title": item.title,
        "source": item.source,
        "url": item.url,
        "related_assets": item.related_assets,
        "impact": item.impact,
        "reason": item.reason,
    }


def _sum_by_type(assets: List[AssetEvaluation], asset_type: str) -> float:
    return sum(asset.current_value_krw for asset in assets if asset.asset_type == asset_type)


def _news_key(item: Dict[str, Any]) -> str:
    return str(item.get("url") or item.get("title") or "")


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
