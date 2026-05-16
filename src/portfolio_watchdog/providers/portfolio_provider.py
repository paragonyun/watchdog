from abc import ABC, abstractmethod
from typing import List

from ..config import AssetConfig


class PortfolioProvider(ABC):
    @abstractmethod
    def get_assets(self) -> List[AssetConfig]:
        raise NotImplementedError
