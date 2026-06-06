import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote, urlencode

import requests

from ..config import AppConfig, AssetConfig
from ..ledger.models import LedgerEvent
from ..models import PriceQuote
from .portfolio_provider import PortfolioProvider
from .price_provider import PriceProvider

logger = logging.getLogger(__name__)
MAX_PAGES_PER_REQUEST = 1000
MIN_CLOSED_ORDER_WINDOW = timedelta(seconds=1)

try:
    import jwt
except Exception:
    jwt = None


def _required_text(row: Dict, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Upbit {field} is required")
    return value


def _number(row: Dict, field: str) -> Decimal:
    try:
        value = Decimal(str(row[field]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Upbit {field} must be numeric") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"Upbit {field} must be a non-negative finite number")
    return value


def _integer(row: Dict, field: str) -> int:
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Upbit {field} must be a non-negative integer")
    return value


def _occurred_at(row: Dict, field: str) -> datetime:
    value = _required_text(row, field)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Upbit {field} must be an ISO datetime") from exc
    if result.tzinfo is None:
        raise ValueError(f"Upbit {field} must include a timezone")
    return result


def parse_upbit_closed_orders(rows: list[dict]) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    seen_event_ids = set()
    for order in rows:
        order_id = _required_text(order, "uuid")
        if _integer(order, "trades_count") == 0:
            continue
        market = _required_text(order, "market")
        if not market.startswith("KRW-") or len(market) == 4:
            raise ValueError("Upbit market must be a KRW asset market")
        asset_symbol = market.split("-", 1)[1]
        side = _required_text(order, "side")
        if side not in {"bid", "ask"}:
            raise ValueError("Upbit side must be bid or ask")
        paid_fee = _number(order, "paid_fee")
        trades = order.get("trades")
        if not isinstance(trades, list):
            raise ValueError("Upbit trades must be a list")

        parsed_trades = []
        for trade in trades:
            parsed_trades.append(
                {
                    "id": _required_text(trade, "uuid"),
                    "price": _number(trade, "price"),
                    "volume": _number(trade, "volume"),
                    "funds": _number(trade, "funds"),
                    "occurred_at": _occurred_at(trade, "created_at"),
                    "fee": _number(trade, "fee") if "fee" in trade else None,
                }
            )

        missing_fee = [trade for trade in parsed_trades if trade["fee"] is None]
        explicit_fee = sum(
            (trade["fee"] for trade in parsed_trades if trade["fee"] is not None),
            Decimal("0"),
        )
        remaining_fee = paid_fee - explicit_fee
        if remaining_fee < 0:
            raise ValueError("Upbit trade fees exceed paid_fee")
        missing_funds = sum((trade["funds"] for trade in missing_fee), Decimal("0"))
        allocated = Decimal("0")
        for index, trade in enumerate(missing_fee):
            if index == len(missing_fee) - 1:
                trade["fee"] = remaining_fee - allocated
            else:
                fee = remaining_fee * trade["funds"] / missing_funds if missing_funds else Decimal("0")
                trade["fee"] = fee
                allocated += fee

        for trade in parsed_trades:
            fee = trade["fee"] or Decimal("0")
            is_buy = side == "bid"
            event_id = f"{order_id}:{trade['id']}"
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            events.append(
                LedgerEvent(
                    provider="upbit",
                    provider_event_id=event_id,
                    occurred_at=trade["occurred_at"],
                    event_type="buy" if is_buy else "sell",
                    asset_symbol=asset_symbol,
                    cash_flow_krw=float(-(trade["funds"] + fee) if is_buy else trade["funds"] - fee),
                    quantity=float(trade["volume"] if is_buy else -trade["volume"]),
                    unit_price_krw=float(trade["price"]),
                    fee_krw=float(fee),
                )
            )
    return events


def _parse_upbit_transfers(
    rows: list[dict], completed_state: str, event_type: str, direction: Decimal
) -> list[LedgerEvent]:
    events = []
    seen_ids = set()
    for row in rows:
        if str(row.get("state", "")).upper() != completed_state:
            continue
        event_id = _required_text(row, "uuid")
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        currency = _required_text(row, "currency").upper()
        amount = _number(row, "amount")
        fee = _number(row, "fee") if event_type == "withdrawal" else Decimal("0")
        occurred_at = _occurred_at(row, "done_at")
        is_krw = currency == "KRW"
        total = amount + fee if event_type == "withdrawal" else amount
        events.append(
            LedgerEvent(
                provider="upbit",
                provider_event_id=event_id,
                occurred_at=occurred_at,
                event_type=event_type,
                asset_symbol=None if is_krw else currency,
                cash_flow_krw=float(total * direction) if is_krw else 0.0,
                quantity=None if is_krw else float(total * direction),
                fee_krw=float(fee) if is_krw else 0.0,
                external_cash_flow=is_krw,
            )
        )
    return events


def parse_upbit_deposits(rows: list[dict]) -> list[LedgerEvent]:
    return _parse_upbit_transfers(rows, "ACCEPTED", "deposit", Decimal("1"))


def parse_upbit_withdraws(rows: list[dict]) -> list[LedgerEvent]:
    return _parse_upbit_transfers(rows, "DONE", "withdrawal", Decimal("-1"))


class UpbitPriceProvider(PriceProvider):
    def __init__(self, fallback_prices: Dict[str, float]) -> None:
        self.fallback_prices = fallback_prices

    def get_prices(self, symbols: List[str]) -> Dict[str, PriceQuote]:
        if not symbols:
            return {}
        markets = [f"KRW-{symbol}" for symbol in symbols]
        result: Dict[str, PriceQuote] = {}
        try:
            response = requests.get("https://api.upbit.com/v1/ticker", params={"markets": ",".join(markets)}, timeout=10)
            response.raise_for_status()
            for item in response.json():
                symbol = str(item["market"]).split("-")[-1]
                result[symbol] = PriceQuote(
                    symbol=symbol,
                    price_krw=float(item["trade_price"]),
                    change_pct_24h=(float(item.get("signed_change_rate", 0.0)) * 100),
                    source="upbit",
                    retrieved_at=datetime.utcnow(),
                )
        except Exception as exc:
            logger.warning("Upbit ticker lookup failed: %s", exc)
        for symbol in symbols:
            if symbol not in result and symbol in self.fallback_prices:
                result[symbol] = PriceQuote(symbol=symbol, price_krw=float(self.fallback_prices[symbol]), source="fallback")
        return result


class UpbitAccountClient:
    def __init__(self, access_key: str, secret_key: str) -> None:
        self.access_key = access_key
        self.secret_key = secret_key

    def get_accounts(self) -> List[Dict]:
        headers = {"Authorization": f"Bearer {self._jwt_token()}"}
        response = requests.get("https://api.upbit.com/v1/accounts", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def list_closed_orders(
        self, start_time: str, end_time: str, limit: int = 100
    ) -> list[dict]:
        _validate_closed_order_limit(limit)
        query = {
            "start_time": start_time,
            "end_time": end_time,
            "limit": str(limit),
            "order_by": "asc",
        }
        return self._request_list("https://api.upbit.com/v1/orders/closed", query)

    def get_order(self, order_uuid: str) -> dict:
        query = {"uuid": _required_text({"uuid": order_uuid}, "uuid")}
        headers = {"Authorization": f"Bearer {self._jwt_token(query)}"}
        response = requests.get(
            "https://api.upbit.com/v1/order", headers=headers, params=query, timeout=10
        )
        response.raise_for_status()
        order = response.json()
        if not isinstance(order, dict):
            raise ValueError("Upbit response must be an object")
        return order

    def list_deposits(self, page: int = 1, limit: int = 100) -> list[dict]:
        query = {"page": str(page), "limit": str(limit)}
        return self._request_list("https://api.upbit.com/v1/deposits", query)

    def list_withdraws(self, page: int = 1, limit: int = 100) -> list[dict]:
        query = {"page": str(page), "limit": str(limit)}
        return self._request_list("https://api.upbit.com/v1/withdraws", query)

    def _request_list(self, url: str, query: Dict[str, Any]) -> list[dict]:
        headers = {"Authorization": f"Bearer {self._jwt_token(query)}"}
        response = requests.get(url, headers=headers, params=query, timeout=10)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Upbit response must be a list")
        return rows

    def _jwt_token(self, query: Optional[Dict[str, Any]] = None) -> str:
        if jwt is None:
            raise RuntimeError("PyJWT가 설치되어 있지 않습니다. Upbit 계좌조회에는 PyJWT가 필요합니다.")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if query:
            query_string = unquote(urlencode(query, doseq=True)).encode()
            payload["query_hash"] = hashlib.sha512(query_string).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        return jwt.encode(payload, self.secret_key, algorithm="HS256")


def _fetch_pages(fetch_page: Callable[[int, int], list[dict]], limit: int) -> list[dict]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    rows: list[dict] = []
    for page in range(1, MAX_PAGES_PER_REQUEST + 1):
        page_rows = fetch_page(page, limit)
        rows.extend(page_rows)
        if len(page_rows) < limit:
            return rows
    raise RuntimeError("Upbit page limit reached")


def _utc_iso(value: datetime) -> str:
    # Collection helpers interpret naive inputs as UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _validate_closed_order_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")


def _fetch_closed_order_window(
    client: UpbitAccountClient, start: datetime, end: datetime, limit: int
) -> list[dict]:
    rows = client.list_closed_orders(start.isoformat(), end.isoformat(), limit)
    if len(rows) < limit:
        return rows
    if len(rows) > limit:
        raise ValueError("Upbit closed orders response exceeds requested limit")
    if end - start <= MIN_CLOSED_ORDER_WINDOW:
        raise RuntimeError("Upbit closed orders minimum window is still saturated")
    midpoint = start + (end - start) / 2
    return _fetch_closed_order_window(client, start, midpoint, limit) + _fetch_closed_order_window(
        client, midpoint, end, limit
    )


def fetch_upbit_closed_orders(
    client: UpbitAccountClient, start_time: datetime, end_time: datetime, limit: int = 100
) -> list[dict]:
    _validate_closed_order_limit(limit)
    start = datetime.fromisoformat(_utc_iso(start_time))
    end = datetime.fromisoformat(_utc_iso(end_time))
    if start >= end:
        raise ValueError("start_time must be before end_time")
    summaries: list[dict] = []
    while start < end:
        chunk_end = min(start + timedelta(days=7), end)
        summaries.extend(_fetch_closed_order_window(client, start, chunk_end, limit))
        start = chunk_end
    details = []
    seen_order_ids = set()
    for summary in summaries:
        order_id = _required_text(summary, "uuid")
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        details.append(client.get_order(order_id))
    return details


def fetch_upbit_deposits(client: UpbitAccountClient, limit: int = 100) -> list[dict]:
    return _fetch_pages(client.list_deposits, limit)


def fetch_upbit_withdraws(client: UpbitAccountClient, limit: int = 100) -> list[dict]:
    return _fetch_pages(client.list_withdraws, limit)


class UpbitPortfolioProvider(PortfolioProvider):
    def __init__(
        self,
        config: AppConfig,
        account_client: UpbitAccountClient,
        fallback_to_config: bool,
        base_provider: PortfolioProvider,
    ) -> None:
        self.config = config
        self.account_client = account_client
        self.fallback_to_config = fallback_to_config
        self.base_provider = base_provider
        self.used_fallback = False
        self.last_error: Optional[str] = None

    def get_assets(self) -> List[AssetConfig]:
        base_assets = self.base_provider.get_assets()
        self.used_fallback = False
        self.last_error = None
        try:
            accounts = self.account_client.get_accounts()
        except Exception as exc:
            self.used_fallback = self.fallback_to_config
            self.last_error = str(exc)
            logger.warning("Upbit account lookup failed: %s", exc)
            if self.fallback_to_config:
                return base_assets
            raise
        balances = {item["currency"].upper(): item for item in accounts}
        result: List[AssetConfig] = []
        for asset in base_assets:
            if asset.asset_type == "coin" and asset.symbol in balances:
                row = balances[asset.symbol]
                result.append(
                    AssetConfig(
                        **{
                            **asset.__dict__,
                            "current_quantity": float(row.get("balance", 0.0)),
                            "average_buy_price_krw": float(row.get("avg_buy_price", 0.0) or 0.0),
                        }
                    )
                )
            else:
                result.append(asset)
        return result
