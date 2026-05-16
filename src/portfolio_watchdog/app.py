import hashlib
import logging
import platform
from pathlib import Path
from typing import Dict, List

from .config import AppConfig, AssetConfig
from .history import HistoryRepository
from .message_format import split_message
from .notifiers.base import Notifier
from .notifiers.console import ConsoleNotifier
from .notifiers.telegram import TelegramNotifier
from .notifiers.windows import WindowsNotifier
from .news_llm import LlmNewsProvider, OpenAiNewsAnalyzer
from .portfolio.calculator import evaluate_portfolio
from .providers.config_portfolio_provider import ConfigPortfolioProvider
from .providers.kis import KisDomesticStockClient, KisPortfolioProvider, KisTokenClient
from .providers.mock_price_provider import MockPriceProvider
from .providers.noop_news_provider import NoopNewsProvider
from .providers.portfolio_provider import PortfolioProvider
from .providers.price_provider import PriceProvider
from .providers.rss_news_provider import RssNewsProvider
from .providers.simple_http_price_provider import SimpleHttpPriceProvider
from .providers.upbit import UpbitAccountClient, UpbitPortfolioProvider, UpbitPriceProvider
from .providers.news_provider import NewsProvider
from .reports import build_asset_status_report, build_news_report, build_portfolio_report
from .repositories.file_snapshot_repository import FileSnapshotRepository
from .rules.engine import RuleEngine
from .weekly_report import build_weekly_report_source, build_weekly_report_telegram_summary, write_weekly_report_source

logger = logging.getLogger(__name__)


class PortfolioWatchdogApp:
    def __init__(self, config: AppConfig, env: Dict[str, str]) -> None:
        self.config = config
        self.env = env
        self.repository = FileSnapshotRepository(self.config.snapshot.path)
        self.history_repository = HistoryRepository(self.config.snapshot.history_path)
        self.portfolio_provider = self._build_portfolio_provider()
        self.news_provider = self._build_news_provider()
        self.fallback_notifier = self._build_fallback_notifier()
        self.notifier = self._build_notifier()
        self.price_provider = self._build_price_provider()
        self.rule_engine = RuleEngine(self.config.alert_settings, self.repository)

    def _build_portfolio_provider(self) -> PortfolioProvider:
        provider: PortfolioProvider = ConfigPortfolioProvider(self.config)
        pc = self.config.portfolio_provider
        if pc.provider_type == "upbit" or pc.coin_provider_type == "upbit":
            access_key, secret_key = self.env.get("UPBIT_ACCESS_KEY"), self.env.get("UPBIT_SECRET_KEY")
            if access_key and secret_key:
                provider = UpbitPortfolioProvider(self.config, UpbitAccountClient(access_key, secret_key), pc.fallback_to_config, provider)
            else:
                logger.warning("Upbit account keys are missing, using configured quantities.")
        if pc.provider_type == "kis" or pc.equity_provider_type == "kis":
            app_key, app_secret = self.env.get("KIS_APP_KEY"), self.env.get("KIS_APP_SECRET")
            account_no, product_code = self.env.get("KIS_ACCOUNT_NO"), self.env.get("KIS_ACCOUNT_PRODUCT_CODE")
            if app_key and app_secret and account_no and product_code:
                token_client = KisTokenClient(app_key, app_secret, env=self.env.get("KIS_ENV", "real"), token_cache_path=self.env.get("KIS_TOKEN_CACHE_PATH", "snapshots/kis_token.json"))
                provider = KisPortfolioProvider(provider, KisDomesticStockClient(token_client, account_no, product_code), pc.fallback_to_config)
            else:
                logger.warning("KIS account settings are missing, using configured equity values.")
        return provider

    def _build_notifier(self) -> Notifier:
        if not self.config.telegram.enabled:
            return self.fallback_notifier
        token, chat_id = self.env.get("TELEGRAM_BOT_TOKEN"), self.env.get("TELEGRAM_CHAT_ID")
        return TelegramNotifier(token, chat_id) if token and chat_id else self.fallback_notifier

    def _build_fallback_notifier(self) -> Notifier:
        return WindowsNotifier() if platform.system() == "Windows" else ConsoleNotifier()

    def _build_price_provider(self) -> PriceProvider:
        if self.config.price_provider.provider_type == "mock":
            return MockPriceProvider(self.config.price_provider.fallback_prices)
        if self.config.price_provider.provider_type == "upbit":
            return UpbitPriceProvider(self.config.price_provider.fallback_prices)
        return SimpleHttpPriceProvider(self.config.price_provider.coin_gecko_ids, self.config.price_provider.fallback_prices)

    def _build_news_provider(self) -> NewsProvider:
        if self.config.news.provider_type == "noop":
            return NoopNewsProvider()
        provider: NewsProvider = RssNewsProvider(self.config.assets, self.config.news.queries, self.config.news.lookback_hours, self.config.news.max_items, self.config.news.max_items_per_query)
        if not self.config.news.llm_enabled:
            return provider
        api_key = self.env.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY is missing, using RSS keyword news analysis.")
            return provider
        return LlmNewsProvider(provider, OpenAiNewsAnalyzer(api_key, self.env.get("OPENAI_MODEL", "gpt-4o-mini"), self.env.get("OPENAI_API_BASE", "https://api.openai.com/v1")), self.config.assets)

    def _resolve_coin_symbols(self, assets: List[AssetConfig]) -> List[str]:
        return [asset.symbol for asset in assets if asset.asset_type == "coin"]

    def _evaluate_current_portfolio(self):
        assets = self.portfolio_provider.get_assets()
        prices = self.price_provider.get_prices(self._resolve_coin_symbols(assets))
        return assets, evaluate_portfolio(assets, prices)

    def run(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logger.info("Portfolio Watchdog 실행 시작")
        assets, portfolio = self._evaluate_current_portfolio()
        alerts = self.rule_engine.evaluate(portfolio, assets)
        news_items = self.news_provider.get_market_summary()
        self.history_repository.append_portfolio(portfolio)
        self.history_repository.append_news(news_items)
        self._notify_safe(build_portfolio_report(portfolio, alerts, news_items))

    def run_news_check(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        news_items = self._filter_new_news_items(self.news_provider.get_market_summary())
        if not news_items:
            logger.info("No new portfolio-related news")
            return
        self.history_repository.append_news(news_items)
        self._notify_safe(build_news_report(news_items))
        logger.info("News report sent: %d items", len(news_items))

    def run_weekly_report(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        _, portfolio = self._evaluate_current_portfolio()
        news_items = self.news_provider.get_market_summary()
        self.history_repository.append_portfolio(portfolio)
        self.history_repository.append_news(news_items)
        state = self.history_repository.load()
        report = build_weekly_report_source(portfolio, state)
        path = write_weekly_report_source(report)
        self._notify_file_safe(path, build_weekly_report_telegram_summary(portfolio, state, path))
        logger.info("Weekly report source created: %s", path)

    def send_sample_reports(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        _, portfolio = self._evaluate_current_portfolio()
        news_items = self.news_provider.get_market_summary()
        report_source = build_weekly_report_source(portfolio, self.history_repository.load())
        report_path = write_weekly_report_source(report_source)
        self._notify_safe(f"<b>[샘플] 1시간 뉴스 샘플</b>\n\n{build_news_report(news_items)}")
        self._notify_safe(f"<b>[샘플] 자산 변동 현황 샘플</b>\n\n{build_asset_status_report(portfolio, [])}")
        self._notify_file_safe(report_path, f"<b>[샘플] 위클리 리포트 자료</b>\n\n{build_weekly_report_telegram_summary(portfolio, self.history_repository.load(), report_path)}")
        logger.info("Sample reports sent: 3")

    def _filter_new_news_items(self, news_items):
        repository = FileSnapshotRepository(self.config.news.snapshot_path)
        state = repository.load()
        seen_keys = set(state.get("seen_news_keys", []))
        new_items = []
        for item in news_items:
            key = hashlib.sha256((item.url or item.title).encode("utf-8")).hexdigest()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            new_items.append(item)
        repository.save({"seen_news_keys": sorted(seen_keys)[-500:]})
        return new_items

    def _notify_safe(self, message: str) -> None:
        for chunk in split_message(message):
            try:
                self.notifier.notify(chunk)
            except Exception:
                logger.exception("Primary notification failed, using fallback notifier.")
                if self.notifier is self.fallback_notifier:
                    ConsoleNotifier().notify(chunk)
                    continue
                try:
                    self.fallback_notifier.notify(chunk)
                except Exception:
                    logger.exception("Fallback notification failed, using console notifier.")
                    ConsoleNotifier().notify(chunk)

    def _notify_file_safe(self, path: Path, caption: str) -> None:
        notify_document = getattr(self.notifier, "notify_document", None)
        if notify_document is None:
            self._notify_safe(f"{caption}\n\n파일 경로: <code>{path}</code>")
            return
        try:
            notify_document(path, caption)
        except Exception:
            logger.exception("Document notification failed, using text fallback.")
            self._notify_safe(f"{caption}\n\n파일 경로: <code>{path}</code>")

    def check_config(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        assets = self.portfolio_provider.get_assets()
        logger.info("설정 확인 중")
        logger.info("자산 수: %d", len(assets))
        logger.info("Telegram 사용 여부: %s", bool(self.config.telegram.enabled and self.env.get("TELEGRAM_BOT_TOKEN") and self.env.get("TELEGRAM_CHAT_ID")))
        logger.info("스냅샷 경로: %s", self.config.snapshot.path)
        for asset in assets:
            logger.info("- %s(%s): target %.2f%%, quantity=%s, manual=%s", asset.symbol, asset.asset_type, asset.target_weight * 100, asset.current_quantity, asset.manual_value_krw)

    def send_test_alert(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        self._notify_safe("Portfolio Watchdog 테스트 알림입니다.")
        logger.info("테스트 알림을 전송했습니다.")
