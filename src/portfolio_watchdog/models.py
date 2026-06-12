from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    differences: dict[str, float]
    tolerance: float


@dataclass
class PriceQuote:
    symbol: str
    price_krw: float
    change_pct_24h: Optional[float] = None
    source: str = "unknown"
    retrieved_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AssetEvaluation:
    symbol: str
    name: str
    asset_type: str
    target_weight: float
    current_quantity: Optional[float]
    manual_value_krw: Optional[float]
    average_buy_price_krw: Optional[float] = None
    profit_loss_krw: Optional[float] = None
    profit_loss_rate_pct: Optional[float] = None
    alert_threshold_percent: float = 0.0
    current_value_krw: float = 0.0
    current_weight: float = 0.0
    weight_diff_pct: float = 0.0
    price_quote: Optional[PriceQuote] = None


@dataclass
class PortfolioEvaluation:
    assets: List[AssetEvaluation]
    total_value_krw: float


@dataclass
class Alert:
    key: str
    title: str
    message: str
    severity: str = "info"


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str = "noop"
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    related_assets: List[str] = field(default_factory=list)
    impact: str = "중립"
    reason: str = ""
