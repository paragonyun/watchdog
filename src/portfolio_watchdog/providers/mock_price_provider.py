from datetime import datetime
from typing import Dict, List

from ..models import PriceQuote
from .price_provider import PriceProvider


class MockPriceProvider(PriceProvider):
    def __init__(self, prices: Dict[str, float]) -> None:
        self.prices = prices

    def get_prices(self, symbols: List[str]) -> Dict[str, PriceQuote]:
        return {
            symbol: PriceQuote(symbol=symbol, price_krw=float(self.prices.get(symbol, 0.0)), source="mock", retrieved_at=datetime.utcnow())
            for symbol in symbols
        }
