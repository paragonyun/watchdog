from abc import ABC, abstractmethod
from typing import List

from ..models import NewsItem


class NewsProvider(ABC):
    @abstractmethod
    def get_market_summary(self) -> List[NewsItem]:
        raise NotImplementedError
