import logging
from datetime import datetime
from typing import Dict, List

import requests

from ..models import PriceQuote
from .price_provider import PriceProvider

logger = logging.getLogger(__name__)


class SimpleHttpPriceProvider(PriceProvider):
    def __init__(self, coin_gecko_ids: Dict[str, str], fallback_prices: Dict[str, float]) -> None:
        self.coin_gecko_ids = coin_gecko_ids
        self.fallback_prices = fallback_prices

    def get_prices(self, symbols: List[str]) -> Dict[str, PriceQuote]:
        result: Dict[str, PriceQuote] = {}
        ids = [self.coin_gecko_ids.get(symbol) for symbol in symbols if self.coin_gecko_ids.get(symbol)]
        if ids:
            try:
                response = requests.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": ",".join(ids), "vs_currencies": "krw", "include_24hr_change": "true"},
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                for symbol in symbols:
                    coin_id = self.coin_gecko_ids.get(symbol)
                    if coin_id in data:
                        result[symbol] = PriceQuote(
                            symbol=symbol,
                            price_krw=float(data[coin_id]["krw"]),
                            change_pct_24h=data[coin_id].get("krw_24h_change"),
                            source="coingecko",
                            retrieved_at=datetime.utcnow(),
                        )
            except Exception as exc:
                logger.warning("CoinGecko lookup failed: %s", exc)
        for symbol in symbols:
            if symbol not in result and symbol in self.fallback_prices:
                result[symbol] = PriceQuote(symbol=symbol, price_krw=float(self.fallback_prices[symbol]), source="fallback")
        return result
