import hashlib
import logging
import platform
from pathlib import Path
from typing import Dict, List

from .config import AppConfig, AssetConfig
from .dashboard_data import build_dashboard_payload, load_dashboard_source_payload, upload_dashboard_payload
from .history import HistoryRepository
from .message_format import split_message
from .news_digest import write_hourly_codex_source
from .notifiers.base import Notifier
from .notifiers.console import ConsoleNotifier
from .notifiers.telegram import TelegramNotifier
from .notifiers.windows import WindowsNotifier
from .news_llm import LlmNewsProvider, OpenAiNewsAnalyzer
from .pdf_report import render_weekly_report_pdf
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
from .report_data import build_portfolio_report_source, build_report_caption, build_report_payload, build_weekly_report_source_from_payload, load_report_payload_for_path, write_report_artifact
from .report_validation import require_valid_report_payload
from .reports import build_asset_status_report, build_news_report, build_portfolio_report
from .repositories.file_snapshot_repository import FileSnapshotRepository
from .rules.engine import RuleEngine
from .weekly_report import build_weekly_report_source, build_weekly_report_telegram_summary, write_weekly_report_source

logger = logging.getLogger(__name__)


class PortfolioWatchdogApp:
    def __init__(self, config: AppConfig, env: Dict[str, str], use_llm_news: bool = True) -> None:
        self.config = config
        self.env = env
        self.use_llm_news = use_llm_news
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
        if not self.use_llm_news or not self.config.news.llm_enabled:
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
        source_path = write_hourly_codex_source(news_items)
        if source_path:
            logger.info("Hourly Codex news source created: %s", source_path)
        logger.info("News report sent: %d items", len(news_items))

    def run_weekly_report(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        path, portfolio, state = self._create_weekly_report_source()
        self._notify_file_safe(path, build_weekly_report_telegram_summary(portfolio, state, path))
        logger.info("Weekly report source sent: %s", path)

    def create_weekly_report_source(self) -> Path:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        path, _, _ = self._create_weekly_report_source()
        logger.info("Weekly report source created: %s", path)
        return path

    def create_portfolio_report_source(self) -> Path:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        _, portfolio = self._evaluate_current_portfolio()
        news_items = self.news_provider.get_market_summary()
        self.history_repository.append_portfolio(portfolio)
        self.history_repository.append_news(news_items)
        payload = build_report_payload(
            "portfolio",
            portfolio,
            self.history_repository.load(),
            news_items,
            provider_status=self._provider_status(),
        )
        require_valid_report_payload(payload)
        artifact = write_report_artifact(build_portfolio_report_source(payload), payload, "portfolio_report_source")
        logger.info("Portfolio report source created: %s", artifact.text_path)
        return artifact.text_path

    def _create_weekly_report_source(self):
        _, portfolio = self._evaluate_current_portfolio()
        news_items = self.news_provider.get_market_summary()
        self.history_repository.append_portfolio(portfolio)
        self.history_repository.append_news(news_items)
        state = self.history_repository.load()
        payload = build_report_payload(
            "weekly",
            portfolio,
            state,
            news_items,
            period_days=7,
            provider_status=self._provider_status(),
        )
        require_valid_report_payload(payload)
        artifact = write_report_artifact(build_weekly_report_source_from_payload(payload), payload, "weekly_report_source")
        return artifact.text_path, portfolio, state

    def send_report_document(self, path: Path) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        report_path = Path(path)
        if not report_path.exists():
            raise FileNotFoundError(f"리포트 파일을 찾을 수 없습니다: {report_path}")
        if not report_path.is_file():
            raise ValueError(f"리포트 경로가 파일이 아닙니다: {report_path}")
        payload = load_report_payload_for_path(report_path)
        if payload is not None:
            require_valid_report_payload(payload)
        caption = build_report_caption(report_path, payload)
        self._notify_file_safe(report_path, caption)
        logger.info("Weekly report document sent: %s", report_path)

    def send_message_file(self, path: Path) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        message_path = Path(path)
        if not message_path.exists():
            raise FileNotFoundError(f"메시지 파일을 찾을 수 없습니다: {message_path}")
        if not message_path.is_file():
            raise ValueError(f"메시지 경로가 파일이 아닙니다: {message_path}")
        self._notify_safe(message_path.read_text(encoding="utf-8"))
        logger.info("Message file sent: %s", message_path)

    def complete_report(self, path: Path, output_path: Path | None = None, sync_dashboard: bool = False) -> Path:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        report_path = Path(path)
        pdf_path = self.render_report_pdf(report_path, output_path)
        self.send_report_document(pdf_path)
        if sync_dashboard:
            self.sync_dashboard(report_path)
        logger.info("Complete report processed: %s", pdf_path)
        return pdf_path

    def sync_dashboard(self, path: Path) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        report_payload = load_dashboard_source_payload(Path(path))
        dashboard_payload = build_dashboard_payload(report_payload)
        result = upload_dashboard_payload(
            dashboard_payload,
            self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
            self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )
        logger.info("Dashboard synced: %s", result)
        return dashboard_payload

    def render_report_pdf(self, path: Path, output_path: Path | None = None) -> Path:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        pdf_path = render_weekly_report_pdf(Path(path), self.history_repository.load(), output_path)
        logger.info("Weekly report PDF created: %s", pdf_path)
        return pdf_path

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
            except Exception as exc:
                logger.warning("Primary notification failed, using fallback notifier: %s", self._safe_error(exc))
                if self.notifier is self.fallback_notifier:
                    ConsoleNotifier().notify(chunk)
                    continue
                try:
                    self.fallback_notifier.notify(chunk)
                except Exception as fallback_exc:
                    logger.warning("Fallback notification failed, using console notifier: %s", self._safe_error(fallback_exc))
                    ConsoleNotifier().notify(chunk)

    def _notify_file_safe(self, path: Path, caption: str) -> None:
        notify_document = getattr(self.notifier, "notify_document", None)
        if notify_document is None:
            self._notify_safe(f"{caption}\n\n파일 경로: <code>{path}</code>")
            return
        try:
            notify_document(path, caption)
        except Exception as exc:
            logger.warning("Document notification failed, using text fallback: %s", self._safe_error(exc))
            self._notify_safe(f"{caption}\n\n파일 경로: <code>{path}</code>")

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc)
        token = self.env.get("TELEGRAM_BOT_TOKEN")
        return message.replace(token, "<redacted>") if token else message

    def _provider_status(self) -> List[Dict[str, object]]:
        result: List[Dict[str, object]] = []
        provider = self.portfolio_provider
        while provider is not None:
            if isinstance(provider, UpbitPortfolioProvider):
                result.append({"provider": "upbit", "used_fallback": provider.used_fallback, "error": provider.last_error})
            if isinstance(provider, KisPortfolioProvider):
                result.append({"provider": "kis", "used_fallback": provider.used_fallback, "error": provider.last_error})
            provider = getattr(provider, "base_provider", None)
        return result

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
