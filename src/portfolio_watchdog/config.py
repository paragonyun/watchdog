import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import dotenv_values

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


@dataclass
class AssetConfig:
    symbol: str
    name: str
    asset_type: str = "coin"
    broker_symbol: Optional[str] = None
    target_weight: float = 0.0
    current_quantity: Optional[float] = None
    manual_value_krw: Optional[float] = None
    average_buy_price_krw: Optional[float] = None
    profit_loss_krw: Optional[float] = None
    profit_loss_rate_pct: Optional[float] = None
    alert_threshold_percent: Optional[float] = None


@dataclass
class PriceProviderConfig:
    provider_type: str = "auto"
    coin_gecko_ids: Dict[str, str] = field(default_factory=dict)
    fallback_prices: Dict[str, float] = field(default_factory=dict)


@dataclass
class PortfolioProviderConfig:
    provider_type: str = "config"
    coin_provider_type: str = "config"
    equity_provider_type: str = "config"
    fallback_to_config: bool = True


@dataclass
class NewsConfig:
    provider_type: str = "rss"
    queries: List[str] = field(default_factory=list)
    lookback_hours: int = 24
    max_items: int = 5
    max_items_per_query: int = 5
    snapshot_path: str = "snapshots/news_state.json"
    llm_enabled: bool = True


@dataclass
class AlertConfig:
    price_change_threshold_percent: float = 5.0
    weight_deviation_threshold_pct: float = 5.0
    total_coin_weight_limit: float = 0.60


@dataclass
class TelegramConfig:
    enabled: bool = False
    chat_id: Optional[str] = None


@dataclass
class SnapshotConfig:
    path: str = "snapshots/state.json"
    history_path: str = "snapshots/history.json"


@dataclass
class AppConfig:
    assets: List[AssetConfig]
    price_provider: PriceProviderConfig
    alert_settings: AlertConfig
    telegram: TelegramConfig
    snapshot: SnapshotConfig
    portfolio_provider: PortfolioProviderConfig = field(default_factory=PortfolioProviderConfig)
    news: NewsConfig = field(default_factory=NewsConfig)


def load_config(path: Path) -> AppConfig:
    raw = _read_yaml(path)
    portfolio = raw.get("portfolio", {})
    providers = raw.get("providers", {})
    return AppConfig(
        assets=_parse_assets(portfolio.get("assets", [])),
        portfolio_provider=_parse_portfolio_provider(providers.get("portfolio", {})),
        price_provider=_parse_price_provider(providers.get("price", {})),
        news=_parse_news_config(providers.get("news", {})),
        alert_settings=_parse_alert_config(raw.get("alerts", {})),
        telegram=_parse_telegram_config(raw.get("telegram", {})),
        snapshot=_parse_snapshot_config(raw.get("snapshot", {})),
    )


def load_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        logger.warning(".env 파일을 찾을 수 없습니다: %s", path)
        return {}
    data = dotenv_values(path)
    return {k: v for k, v in data.items() if k and v is not None}


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError("설정 파일이 올바른 YAML 형식이 아닙니다.")
    return data


def _parse_assets(raw_assets: List[Dict[str, Any]]) -> List[AssetConfig]:
    assets: List[AssetConfig] = []
    for item in raw_assets:
        symbol = str(item.get("symbol", "")).upper().strip()
        if not symbol:
            raise ConfigError("자산 symbol은 필수입니다.")
        assets.append(
            AssetConfig(
                symbol=symbol,
                name=str(item.get("name", "")),
                asset_type=str(item.get("asset_type", "coin")),
                broker_symbol=(None if item.get("broker_symbol") is None else str(item.get("broker_symbol")).upper().strip()),
                target_weight=float(item.get("target_weight", 0.0)),
                current_quantity=(None if item.get("current_quantity") is None else float(item.get("current_quantity"))),
                manual_value_krw=(None if item.get("manual_value_krw") is None else float(item.get("manual_value_krw"))),
                average_buy_price_krw=(None if item.get("average_buy_price_krw") is None else float(item.get("average_buy_price_krw"))),
                profit_loss_krw=(None if item.get("profit_loss_krw") is None else float(item.get("profit_loss_krw"))),
                profit_loss_rate_pct=(None if item.get("profit_loss_rate_pct") is None else float(item.get("profit_loss_rate_pct"))),
                alert_threshold_percent=(None if item.get("alert_threshold_percent") is None else float(item.get("alert_threshold_percent"))),
            )
        )
    if not assets:
        raise ConfigError("포트폴리오 자산이 설정되어 있지 않습니다.")
    return assets


def _parse_price_provider(raw: Dict[str, Any]) -> PriceProviderConfig:
    return PriceProviderConfig(
        provider_type=str(raw.get("type", "auto")),
        coin_gecko_ids=raw.get("coin_gecko_ids", {}) or {},
        fallback_prices={k.upper(): float(v) for k, v in (raw.get("fallback_prices", {}) or {}).items()},
    )


def _parse_portfolio_provider(raw: Dict[str, Any]) -> PortfolioProviderConfig:
    provider_type = str(raw.get("type", "config"))
    return PortfolioProviderConfig(
        provider_type=provider_type,
        coin_provider_type=str(raw.get("coin_type", "config")),
        equity_provider_type=str(raw.get("equity_type", "config")),
        fallback_to_config=_parse_bool(raw.get("fallback_to_config", True)),
    )


def _parse_news_config(raw: Dict[str, Any]) -> NewsConfig:
    queries = raw.get("queries", [])
    return NewsConfig(
        provider_type=str(raw.get("type", "rss")),
        queries=[str(item) for item in queries] if isinstance(queries, list) else [],
        lookback_hours=int(raw.get("lookback_hours", 24)),
        max_items=int(raw.get("max_items", 5)),
        max_items_per_query=int(raw.get("max_items_per_query", 5)),
        snapshot_path=str(raw.get("snapshot_path", "snapshots/news_state.json")),
        llm_enabled=_parse_bool(raw.get("llm_enabled", True)),
    )


def _parse_alert_config(raw: Dict[str, Any]) -> AlertConfig:
    return AlertConfig(
        price_change_threshold_percent=float(raw.get("price_change_threshold_percent", 5.0)),
        weight_deviation_threshold_pct=float(raw.get("weight_deviation_threshold_pct", 5.0)),
        total_coin_weight_limit=float(raw.get("total_coin_weight_limit", 0.60)),
    )


def _parse_telegram_config(raw: Dict[str, Any]) -> TelegramConfig:
    return TelegramConfig(enabled=_parse_bool(raw.get("enabled", False)), chat_id=None if raw.get("chat_id") is None else str(raw.get("chat_id")))


def _parse_snapshot_config(raw: Dict[str, Any]) -> SnapshotConfig:
    return SnapshotConfig(path=str(raw.get("path", "snapshots/state.json")), history_path=str(raw.get("history_path", "snapshots/history.json")))


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
