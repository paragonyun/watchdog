from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class LedgerEvent:
    provider: str
    provider_event_id: str
    occurred_at: datetime
    event_type: str
    asset_symbol: Optional[str]
    cash_flow_krw: float
    quantity: Optional[float] = None
    unit_price_krw: Optional[float] = None
    fee_krw: float = 0.0
    external_cash_flow: bool = False
    memo: Optional[str] = None


@dataclass(frozen=True)
class AccountSnapshot:
    provider: str
    captured_at: datetime
    total_value_krw: float
    data_status: str


@dataclass(frozen=True)
class AssetSnapshot:
    provider: str
    captured_at: datetime
    asset_symbol: str
    asset_type: str
    value_krw: float
    quantity: Optional[float]
    unit_price_krw: Optional[float]
    average_buy_price_krw: Optional[float]
    data_status: str
