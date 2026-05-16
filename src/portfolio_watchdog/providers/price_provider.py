from abc import ABC, abstractmethod
from typing import Dict, List

from ..models import PriceQuote


class PriceProvider(ABC):
    @abstractmethod
    def get_prices(self, symbols: List[str]) -> Dict[str, PriceQuote]:
        raise NotImplementedError
