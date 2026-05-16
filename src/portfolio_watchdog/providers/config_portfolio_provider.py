from typing import List

from ..config import AppConfig, AssetConfig
from .portfolio_provider import PortfolioProvider


class ConfigPortfolioProvider(PortfolioProvider):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def get_assets(self) -> List[AssetConfig]:
        return list(self.config.assets)
