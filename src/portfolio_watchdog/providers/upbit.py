import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests

from ..config import AppConfig, AssetConfig
from ..models import PriceQuote
from .portfolio_provider import PortfolioProvider
from .price_provider import PriceProvider

logger = logging.getLogger(__name__)

try:
    import jwt
except Exception:
    jwt = None


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

    def _jwt_token(self, query: Optional[Dict[str, str]] = None) -> str:
        if jwt is None:
            raise RuntimeError("PyJWT가 설치되어 있지 않습니다. Upbit 계좌조회에는 PyJWT가 필요합니다.")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if query:
            query_string = urlencode(query).encode()
            payload["query_hash"] = hashlib.sha512(query_string).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        return jwt.encode(payload, self.secret_key, algorithm="HS256")


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
