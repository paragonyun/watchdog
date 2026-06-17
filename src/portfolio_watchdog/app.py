import hashlib
import json
import logging
import math
import platform
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import AppConfig, AssetConfig
from .dashboard_data import build_dashboard_payload, build_dashboard_payload_v2, load_dashboard_source_payload, upload_dashboard_payload
from .economic_calendar import build_economic_calendar_payload
from .history import HistoryRepository
from .investment_opinion import build_investment_opinion_payload
from .ledger.import_history import import_history_json
from .ledger.ingestion import add_manual_cash_flow
from .ledger.models import AccountSnapshot, AssetSnapshot, LedgerEvent
from .ledger.reconciliation import reconcile_asset_quantities
from .ledger.repository import LedgerRepository
from .message_format import split_message
from .models import ReconciliationResult
from .news_analysis import risk_news_queries
from .news_digest import write_hourly_codex_source
from .news_risk import (
    build_news_risk_payload,
    load_json_object,
    merge_codex_news_risks,
    save_news_risk_payload,
    validate_news_risk_payload,
)
from .notifiers.base import Notifier
from .notifiers.console import ConsoleNotifier
from .notifiers.telegram import TelegramNotifier
from .notifiers.windows import WindowsNotifier
from .news_llm import LlmNewsProvider, OpenAiNewsAnalyzer
from .pdf_report import render_weekly_report_pdf
from .performance.benchmark import BenchmarkWeight
from .performance.service import build_performance_summary, save_dashboard_payload_v2
from .performance.twr import ValuationPoint
from .portfolio.calculator import evaluate_portfolio
from .providers.config_portfolio_provider import ConfigPortfolioProvider
from .providers.kis import KST, KisDomesticStockClient, KisPortfolioProvider, KisTokenClient, parse_kis_daily_executions
from .providers.mock_price_provider import MockPriceProvider
from .providers.noop_news_provider import NoopNewsProvider
from .providers.portfolio_provider import PortfolioProvider
from .providers.price_provider import PriceProvider
from .providers.rss_news_provider import RssNewsProvider
from .providers.simple_http_price_provider import SimpleHttpPriceProvider
from .providers.upbit import (
    UpbitAccountClient,
    UpbitPortfolioProvider,
    UpbitPriceProvider,
    fetch_upbit_closed_orders,
    fetch_upbit_deposits,
    fetch_upbit_withdraws,
    parse_upbit_closed_orders,
    parse_upbit_deposits,
    parse_upbit_withdraws,
)
from .providers.news_provider import NewsProvider
from .report_data import build_portfolio_report_source, build_report_caption, build_report_payload, build_weekly_report_source_from_payload, load_report_payload_for_path, write_report_artifact
from .report_archive import build_report_archive_payload
from .research_report import build_research_report_payload
from .report_validation import require_valid_report_payload
from .reports import build_asset_status_report, build_news_report, build_portfolio_report
from .repositories.file_snapshot_repository import FileSnapshotRepository
from .rules.engine import RuleEngine
from .weekly_report import build_weekly_report_source, build_weekly_report_telegram_summary, write_weekly_report_source

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("occurred_at must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cursor_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _latest_portfolio_account(
    snapshots: List[AccountSnapshot],
) -> AccountSnapshot | None:
    portfolio = [
        snapshot
        for snapshot in snapshots
        if snapshot.provider == "portfolio" and snapshot.data_status == "actual"
    ]
    return portfolio[-1] if portfolio else None


def _latest_actual_at(snapshots: List[AccountSnapshot]) -> datetime | None:
    actual = [
        snapshot.captured_at
        for snapshot in snapshots
        if snapshot.data_status == "actual"
    ]
    return max(actual, key=_as_utc) if actual else None


def _valuation_points(
    repository: LedgerRepository,
    accounts: List[AccountSnapshot],
    events: List[LedgerEvent],
    latest_reconciliation_status: str,
    tolerance: float,
) -> List[ValuationPoint]:
    external_events = [event for event in events if event.external_cash_flow]
    points = []
    previous_account = None
    for index, account in enumerate(accounts):
        cash_flow = (
            0.0
            if previous_account is None
            else math.fsum(
                event.cash_flow_krw
                for event in external_events
                if _as_utc(previous_account.captured_at) < _as_utc(event.occurred_at)
                <= _as_utc(account.captured_at)
            )
        )
        reconciliation_status = (
            latest_reconciliation_status
            if index == len(accounts) - 1
            else "reconciled"
        )
        if account.data_status != "actual" or cash_flow != 0:
            reconciliation_status = "reconciliation_required"
        if previous_account is not None:
            interval = _reconcile_account_pair(
                repository, previous_account, account, tolerance
            )
            if interval.status != "reconciled":
                reconciliation_status = "reconciliation_required"
        points.append(
            ValuationPoint(
                captured_at=account.captured_at,
                total_value_krw=account.total_value_krw,
                external_cash_flow_krw=cash_flow,
                reconciliation_status=reconciliation_status,
            )
        )
        previous_account = account
    return points


def _reconcile_stored_portfolio_quantities(
    repository: LedgerRepository,
    accounts: List[AccountSnapshot],
    tolerance: float,
) -> ReconciliationResult:
    if len(accounts) < 2:
        return ReconciliationResult("reconciled", {}, tolerance)
    previous_account, latest_account = accounts[-2:]
    return _reconcile_account_pair(repository, previous_account, latest_account, tolerance)


def _reconcile_account_pair(
    repository: LedgerRepository,
    previous_account: AccountSnapshot,
    latest_account: AccountSnapshot,
    tolerance: float,
) -> ReconciliationResult:
    latest_assets = [
        asset
        for asset in repository.list_asset_snapshots(latest_account.captured_at)
        if asset.provider == "portfolio" and asset.quantity is not None
    ]
    actual = {asset.asset_symbol: asset.quantity for asset in latest_assets}
    previous = {
        asset.asset_symbol: asset.quantity
        for asset in repository.list_asset_snapshots(previous_account.captured_at)
        if asset.provider == "portfolio"
        and asset.quantity is not None
    }
    deltas: dict[str, list[float]] = defaultdict(list)
    for event in repository.list_events(
        previous_account.captured_at, latest_account.captured_at
    ):
        if (
            event.asset_symbol is not None
            and event.quantity is not None
            and _as_utc(event.occurred_at) > _as_utc(previous_account.captured_at)
        ):
            deltas[event.asset_symbol].append(event.quantity)
    return reconcile_asset_quantities(
        previous,
        {symbol: math.fsum(values) for symbol, values in deltas.items()},
        actual,
        tolerance,
    )


def _asset_group(asset_type: str) -> str:
    return "isa" if asset_type == "equity" else asset_type


def _profit_loss_rate(snapshot: AssetSnapshot) -> float | None:
    if (
        snapshot.quantity is None
        or snapshot.average_buy_price_krw is None
        or snapshot.quantity <= 0
        or snapshot.average_buy_price_krw <= 0
    ):
        return None
    cost = snapshot.quantity * snapshot.average_buy_price_krw
    return (snapshot.value_krw - cost) / cost * 100


def _safe_provider_status(
    statuses: List[Dict[str, object]] | None,
    portfolio_status: str,
    last_actual_at: datetime | None,
) -> List[Dict[str, object]]:
    last_actual = last_actual_at.isoformat(timespec="seconds") if last_actual_at else None
    if not statuses:
        return [
            {
                "provider": "portfolio",
                "status": portfolio_status,
                "used_fallback": portfolio_status == "fallback",
                "last_actual_at": last_actual,
            }
        ]
    return [
        {
            "provider": str(item.get("provider") or "unknown"),
            "status": "fallback" if item.get("used_fallback") else "actual",
            "used_fallback": bool(item.get("used_fallback")),
            "last_actual_at": last_actual,
        }
        for item in statuses
    ]


def _refresh_step(
    name: str,
    status: str,
    payload: Dict[str, object] | None = None,
    path: Path | None = None,
) -> Dict[str, object]:
    step: Dict[str, object] = {"name": name, "status": status}
    if payload is not None:
        schema = payload.get("schema_version")
        if isinstance(schema, str):
            step["schema_version"] = schema
    if path is not None:
        step["path"] = str(path)
    return step


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
        self._ledger_repository: Optional[LedgerRepository] = None

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

    @property
    def ledger_path(self) -> Path:
        return Path(self.env.get("WATCHDOG_LEDGER_PATH") or self.config.ledger.path)

    @property
    def ledger_repository(self) -> LedgerRepository:
        if self._ledger_repository is None:
            self._ledger_repository = LedgerRepository(self.ledger_path)
        return self._ledger_repository

    def add_cash_flow(self, amount: float, occurred_at: datetime, memo: str) -> bool:
        occurred_at = _as_utc(occurred_at)
        key_material = f"{float(amount):.17g}\n{occurred_at.isoformat()}\n{memo}"
        idempotency_key = f"manual:{hashlib.sha256(key_material.encode('utf-8')).hexdigest()}"
        return add_manual_cash_flow(
            self.ledger_repository,
            occurred_at,
            amount,
            memo,
            idempotency_key,
        )

    def sync_ledger(self, sync_dashboard: bool = False) -> Dict[str, object]:
        payload = self._sync_ledger_payload()
        if sync_dashboard:
            upload_dashboard_payload(
                payload,
                self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
                self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )
        return payload

    def refresh_dashboard(self, sync_codex: bool = True) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        result: Dict[str, object] = {
            "schema_version": "dashboard_refresh_v1",
            "generated_at": _utc_now().isoformat(),
            "steps": [],
        }
        steps = result["steps"]
        assert isinstance(steps, list)

        ledger_payload = self.sync_ledger(sync_dashboard=True)
        steps.append(_refresh_step("ledger", "completed", ledger_payload))

        news_payload = self.collect_news_risks(sync_dashboard=True)
        steps.append(_refresh_step("news_risks", "completed", news_payload))

        if not sync_codex:
            logger.info("Dashboard refresh completed without Codex artifact sync")
            return result

        self._sync_optional_codex_artifacts(steps)
        logger.info("Dashboard refresh completed: %s", result)
        return result

    def prepare_codex_inputs(self) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        ledger_payload = self.sync_ledger(sync_dashboard=True)
        news_payload = self.collect_news_risks(sync_dashboard=True)
        report_source = self.create_portfolio_report_source()
        payload = {
            "schema_version": "codex_dashboard_inputs_v1",
            "generated_at": _utc_now().isoformat(),
            "inputs": {
                "dashboard_v2": str(self.ledger_path.parent / "dashboard_v2_latest.json"),
                "news_risk": str(self._news_risk_output_path()),
                "portfolio_report_source": str(report_source),
            },
            "expected_outputs": {
                "news_risk": str(self._codex_news_risk_path()),
                "opinion": str(self._codex_opinion_path()),
                "calendar": str(self._codex_calendar_path()),
                "research_report": str(self._codex_report_path()),
            },
            "latest_payloads": {
                "dashboard_schema": ledger_payload.get("schema_version"),
                "news_risk_schema": news_payload.get("schema_version"),
            },
            "instructions": [
                "Create codex_news_risk_v1 at expected_outputs.news_risk when deeper news-risk judgment is needed.",
                "Create codex_investment_opinion_v1 at expected_outputs.opinion for buy/sell/observe decisions.",
                "Create codex_economic_calendar_v1 at expected_outputs.calendar for upcoming macro events.",
                "Create dashboard_report_v2 at expected_outputs.research_report for the completed analyst-style report.",
                "Then run refresh-dashboard to validate and upload available outputs.",
            ],
        }
        path = self._codex_inputs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Codex input manifest created: %s", path)
        return payload

    def _sync_optional_codex_artifacts(self, steps: List[Dict[str, object]]) -> None:
        codex_news = self._codex_news_risk_path()
        if codex_news.exists():
            steps.append(_refresh_step("codex_news_risks", "completed", self.merge_news_risks(codex_news, sync_dashboard=True)))
        else:
            steps.append(_refresh_step("codex_news_risks", "skipped", path=codex_news))

        opinion = self._codex_opinion_path()
        if opinion.exists():
            steps.append(_refresh_step("opinion", "completed", self.sync_opinions(opinion)))
        else:
            steps.append(_refresh_step("opinion", "skipped", path=opinion))

        calendar = self._codex_calendar_path()
        if calendar.exists():
            steps.append(_refresh_step("calendar", "completed", self.sync_calendar(calendar)))
        else:
            steps.append(_refresh_step("calendar", "skipped", path=calendar))

        report = self._latest_codex_report_path()
        if report is not None:
            steps.append(_refresh_step("research_report", "completed", self.sync_report(report), path=report))
        else:
            steps.append(_refresh_step("research_report", "skipped", path=self._codex_report_path()))

    def _codex_workspace_path(self) -> Path:
        return Path(self.config.snapshot.path).parent

    def _codex_inputs_path(self) -> Path:
        return self._codex_workspace_path() / "codex_dashboard_inputs_latest.json"

    def _codex_news_risk_path(self) -> Path:
        return self._codex_workspace_path() / "codex_news_risk.json"

    def _codex_opinion_path(self) -> Path:
        return self._codex_workspace_path() / "codex_investment_opinion.json"

    def _codex_calendar_path(self) -> Path:
        return self._codex_workspace_path() / "economic_calendar.json"

    def _codex_report_path(self) -> Path:
        return Path("reports") / "dashboard_report_v2_latest.json"

    def _latest_codex_report_path(self) -> Path | None:
        preferred = self._codex_report_path()
        if preferred.exists():
            return preferred
        reports_dir = preferred.parent
        if not reports_dir.exists():
            return None
        candidates = sorted(
            reports_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("schema_version") == "dashboard_report_v2":
                return path
        return None

    def _sync_ledger_payload(self) -> Dict[str, object]:
        now = _as_utc(_utc_now())
        repository = self.ledger_repository
        history_path = Path(self.config.snapshot.history_path)
        if history_path.exists():
            import_history_json(history_path, repository)

        self._save_target_allocation(repository, now)
        previous_account = _latest_portfolio_account(repository.list_account_snapshots())
        self._sync_provider_events(repository, now)
        assets, portfolio = self._evaluate_current_portfolio()
        raw_provider_status = self._provider_status()
        portfolio_status = (
            "fallback"
            if any(item.get("used_fallback") for item in raw_provider_status)
            else "actual"
        )
        last_actual_at = (
            _latest_actual_at(repository.list_account_snapshots())
            if portfolio_status == "fallback"
            else now
        )
        repository.upsert_snapshot(
            AccountSnapshot(
                provider="portfolio",
                captured_at=now,
                total_value_krw=portfolio.total_value_krw,
                data_status=portfolio_status,
            ),
            [
                AssetSnapshot(
                    provider="portfolio",
                    captured_at=now,
                    asset_symbol=asset.symbol,
                    asset_type=asset.asset_type,
                    value_krw=asset.current_value_krw,
                    quantity=asset.current_quantity,
                    unit_price_krw=(
                        asset.price_quote.price_krw
                        if asset.price_quote is not None
                        else None
                    ),
                    average_buy_price_krw=asset.average_buy_price_krw,
                    data_status=portfolio_status,
                )
                for asset in portfolio.assets
            ],
        )
        reconciliation = self._reconcile_current_quantities(
            repository, previous_account, assets, now
        )
        summary = self._performance_summary_from_ledger(
            repository,
            generated_at=now,
            reconciliation_status=reconciliation.status,
            portfolio_status=portfolio_status,
            last_actual_at=last_actual_at,
            provider_status=raw_provider_status,
        )
        payload = build_dashboard_payload_v2(summary)
        save_dashboard_payload_v2(
            payload, self.ledger_path.parent / "dashboard_v2_latest.json"
        )
        return payload

    def performance_summary(self) -> Dict[str, object]:
        return self._performance_summary_from_ledger(
            self.ledger_repository,
            generated_at=_as_utc(_utc_now()),
        )

    def _sync_provider_events(
        self, repository: LedgerRepository, now: datetime
    ) -> None:
        upbit_client, kis_client = self._provider_clients()
        portfolio_config = self.config.portfolio_provider
        upbit_configured = (
            portfolio_config.provider_type == "upbit"
            or portfolio_config.coin_provider_type == "upbit"
        )
        kis_configured = (
            portfolio_config.provider_type == "kis"
            or portfolio_config.equity_provider_type == "kis"
        )
        if upbit_configured and upbit_client is None:
            raise RuntimeError("Upbit provider is configured but its client is unavailable")
        if kis_configured and kis_client is None:
            raise RuntimeError("KIS provider is configured but its client is unavailable")
        if upbit_client is not None:
            self._sync_upbit_events(repository, upbit_client, now)
        if kis_client is not None:
            self._sync_kis_events(repository, kis_client, now)

    def _provider_clients(self):
        upbit_client = None
        kis_client = None
        provider = self.portfolio_provider
        while provider is not None:
            if upbit_client is None and hasattr(provider, "account_client"):
                upbit_client = provider.account_client
            if kis_client is None and hasattr(provider, "stock_client"):
                kis_client = provider.stock_client
            provider = getattr(provider, "base_provider", None)
        return upbit_client, kis_client

    def _sync_upbit_events(
        self, repository: LedgerRepository, client, now: datetime
    ) -> None:
        checkpoint = now.isoformat()
        order_cursor = _cursor_datetime(repository.get_cursor("upbit", "closed_orders"))
        order_start = max(
            order_cursor - timedelta(days=7) if order_cursor else now - timedelta(days=7),
            now - timedelta(days=90),
        )
        order_rows = (
            fetch_upbit_closed_orders(client, order_start, now)
            if order_start < now
            else []
        )
        repository.upsert_event_page(
            parse_upbit_closed_orders(order_rows),
            "upbit",
            "closed_orders",
            checkpoint,
            now,
        )
        for stream, fetch, parse in (
            ("deposits", fetch_upbit_deposits, parse_upbit_deposits),
            ("withdraws", fetch_upbit_withdraws, parse_upbit_withdraws),
        ):
            cursor = _cursor_datetime(repository.get_cursor("upbit", stream))
            overlap_start = (
                cursor - timedelta(days=7) if cursor else now - timedelta(days=7)
            )
            events = [
                event
                for event in parse(fetch(client))
                if _as_utc(event.occurred_at) >= overlap_start
                and _as_utc(event.occurred_at) <= now
            ]
            repository.upsert_event_page(events, "upbit", stream, checkpoint, now)

    def _sync_kis_events(
        self, repository: LedgerRepository, client, now: datetime
    ) -> None:
        cursor = _cursor_datetime(repository.get_cursor("kis", "daily_executions"))
        today = now.astimezone(KST).date()
        earliest = today - timedelta(days=90)
        start = max(
            earliest,
            (
                (cursor - timedelta(days=7)).astimezone(KST).date()
                if cursor
                else today - timedelta(days=7)
            ),
        )
        rows = client.get_daily_executions(
            start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
        )
        mapping = {
            asset.broker_symbol: asset.symbol
            for asset in self.config.assets
            if asset.broker_symbol
        }
        events = [
            event
            for event in parse_kis_daily_executions(rows, mapping)
            if _as_utc(event.occurred_at) <= now
        ]
        repository.upsert_event_page(
            events, "kis", "daily_executions", now.isoformat(), now
        )

    def _reconcile_current_quantities(
        self,
        repository: LedgerRepository,
        previous_account: AccountSnapshot | None,
        current_assets: List[AssetConfig],
        now: datetime,
    ) -> ReconciliationResult:
        tolerance = self.config.ledger.reconciliation_quantity_tolerance
        if previous_account is None:
            return ReconciliationResult("reconciled", {}, tolerance)
        actual = {
            asset.symbol: asset.current_quantity
            for asset in current_assets
            if asset.current_quantity is not None
        }
        previous = {
            asset.asset_symbol: asset.quantity
            for asset in repository.list_asset_snapshots(previous_account.captured_at)
            if asset.provider == "portfolio"
            and asset.quantity is not None
        }
        deltas: dict[str, list[float]] = defaultdict(list)
        for event in repository.list_events(previous_account.captured_at, now):
            if (
                event.asset_symbol is not None
                and event.quantity is not None
                and _as_utc(event.occurred_at) > _as_utc(previous_account.captured_at)
            ):
                deltas[event.asset_symbol].append(event.quantity)
        return reconcile_asset_quantities(
            previous,
            {symbol: math.fsum(values) for symbol, values in deltas.items()},
            actual,
            tolerance,
        )

    def _save_target_allocation(
        self, repository: LedgerRepository, now: datetime
    ) -> None:
        targets = {"coin": 0.0, "isa": 0.0, "cash": 0.0}
        for asset in self.config.assets:
            group = _asset_group(asset.asset_type)
            if group in targets:
                targets[group] += asset.target_weight
        if not any(targets.values()):
            return
        benchmarks = {
            "coin": "btc_krw",
            "isa": "sp500_krw",
            "cash": "cash_zero",
        }
        try:
            repository.save_target_allocation(
                [
                    BenchmarkWeight(
                        now.astimezone(KST).date(),
                        group,
                        targets[group],
                        benchmarks[group],
                    )
                    for group in ("coin", "isa", "cash")
                ]
            )
        except ValueError as error:
            if "conflict" not in str(error):
                raise
            logger.warning("Target allocation changed within the same KST date; keeping existing version")

    def _performance_summary_from_ledger(
        self,
        repository: LedgerRepository,
        generated_at: datetime,
        reconciliation_status: str | None = None,
        portfolio_status: str | None = None,
        last_actual_at: datetime | None = None,
        provider_status: List[Dict[str, object]] | None = None,
    ) -> Dict[str, object]:
        all_accounts = repository.list_account_snapshots()
        accounts = [
            item
            for item in all_accounts
            if item.provider == "portfolio"
        ]
        latest = accounts[-1] if accounts else None
        if reconciliation_status is None:
            actual_accounts = [
                account for account in accounts if account.data_status == "actual"
            ]
            reconciliation_status = _reconcile_stored_portfolio_quantities(
                repository,
                actual_accounts,
                self.config.ledger.reconciliation_quantity_tolerance,
            ).status
        if portfolio_status is None:
            portfolio_status = (
                latest.data_status
                if latest is not None and latest.data_status in {"actual", "fallback"}
                else "stale"
            )
        if last_actual_at is None:
            last_actual_at = _latest_actual_at(all_accounts)
        points = _valuation_points(
            repository,
            accounts,
            repository.list_events(),
            reconciliation_status,
            self.config.ledger.reconciliation_quantity_tolerance,
        )
        month_points = [
            point
            for point in points
            if (point.captured_at.year, point.captured_at.month)
            == (generated_at.year, generated_at.month)
        ]
        latest_assets = (
            [
                asset
                for asset in repository.list_asset_snapshots(latest.captured_at)
                if asset.provider == "portfolio"
            ]
            if latest is not None
            else []
        )
        asset_groups, assets = self._snapshot_summaries(latest_assets)
        return build_performance_summary(
            valuation_points=points,
            month_points=month_points,
            benchmark_return=None,
            asset_groups=asset_groups,
            assets=assets,
            provider_status=_safe_provider_status(
                provider_status,
                portfolio_status,
                last_actual_at,
            ),
            generated_at=generated_at,
            portfolio_status=portfolio_status,
            last_actual_at=last_actual_at,
            reconciliation_status=reconciliation_status,
        )

    def _snapshot_summaries(
        self, snapshots: List[AssetSnapshot]
    ) -> tuple[List[Dict[str, object]], List[Dict[str, object]]]:
        total = math.fsum(snapshot.value_krw for snapshot in snapshots)
        config_by_symbol = {asset.symbol: asset for asset in self.config.assets}
        assets: List[Dict[str, object]] = []
        values: dict[str, float] = defaultdict(float)
        targets: dict[str, float] = defaultdict(float)
        for config_asset in self.config.assets:
            targets[_asset_group(config_asset.asset_type)] += config_asset.target_weight
        for snapshot in snapshots:
            config_asset = config_by_symbol.get(snapshot.asset_symbol)
            weight_percent = snapshot.value_krw / total * 100 if total else 0.0
            target_weight = config_asset.target_weight if config_asset else 0.0
            item: Dict[str, object] = {
                "symbol": snapshot.asset_symbol,
                "name": config_asset.name if config_asset else snapshot.asset_symbol,
                "asset_type": snapshot.asset_type,
                "value_krw": snapshot.value_krw,
                "weight_percent": weight_percent,
                "target_diff_percentage_points": weight_percent - target_weight * 100,
            }
            profit_rate = _profit_loss_rate(snapshot)
            if profit_rate is not None:
                item["profit_loss_rate_percent"] = profit_rate
            assets.append(item)
            values[_asset_group(snapshot.asset_type)] += snapshot.value_krw
        groups = []
        for group in ("coin", "isa", "cash"):
            if group not in values and group not in targets:
                continue
            weight_percent = values[group] / total * 100 if total else 0.0
            groups.append(
                {
                    "asset_group": group,
                    "value_krw": values[group],
                    "weight_percent": weight_percent,
                    "target_diff_percentage_points": weight_percent
                    - targets[group] * 100,
                }
            )
        return groups, assets

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
            self.sync_report(report_path)
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

    def sync_report(self, path: Path) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        report_path = Path(path)
        if not report_path.exists():
            raise FileNotFoundError(f"리포트 동기화 원본을 찾을 수 없습니다: {report_path}")
        if not report_path.is_file():
            raise ValueError(f"리포트 동기화 경로가 파일이 아닙니다: {report_path}")
        if report_path.suffix.lower() == ".json":
            archive_payload = build_research_report_payload(
                json.loads(report_path.read_text(encoding="utf-8"))
            )
        else:
            source_payload = load_report_payload_for_path(report_path)
            if source_payload is None:
                raise ValueError(f"리포트 payload JSON을 찾을 수 없습니다: {report_path}")
            archive_payload = build_report_archive_payload(
                report_path.read_text(encoding="utf-8"),
                source_payload,
                report_path.name,
            )
        result = upload_dashboard_payload(
            archive_payload,
            self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
            self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )
        logger.info("Report synced: %s", result)
        return archive_payload

    def sync_opinions(self, path: Path) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        opinion_path = Path(path)
        if not opinion_path.exists():
            raise FileNotFoundError(f"Codex opinion JSON not found: {opinion_path}")
        if not opinion_path.is_file():
            raise ValueError(f"Codex opinion path is not a file: {opinion_path}")
        payload = build_investment_opinion_payload(
            json.loads(opinion_path.read_text(encoding="utf-8"))
        )
        result = upload_dashboard_payload(
            payload,
            self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
            self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )
        logger.info("Codex opinions synced: %s", result)
        return payload

    def sync_calendar(self, path: Path) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        calendar_path = Path(path)
        if not calendar_path.exists():
            raise FileNotFoundError(f"Economic calendar JSON not found: {calendar_path}")
        if not calendar_path.is_file():
            raise ValueError(f"Economic calendar path is not a file: {calendar_path}")
        payload = build_economic_calendar_payload(
            json.loads(calendar_path.read_text(encoding="utf-8"))
        )
        result = upload_dashboard_payload(
            payload,
            self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
            self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )
        logger.info("Economic calendar synced: %s", result)
        return payload

    def collect_news_risks(self, output_path: Path | None = None, sync_dashboard: bool = False) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        target = Path(output_path) if output_path else self._news_risk_output_path()
        _, portfolio = self._evaluate_current_portfolio()
        provider = RssNewsProvider(self.config.assets, risk_news_queries(), 72, 60, 5)
        try:
            news_items = provider.get_market_summary()
            if getattr(provider, "all_queries_failed", False):
                raise RuntimeError("all news risk RSS queries failed")
        except Exception:
            if not target.exists():
                raise
            logger.exception("News risk RSS collection failed; preserving existing payload as delayed")
            payload = load_json_object(target)
            validate_news_risk_payload(payload)
            payload["status"] = "delayed"
            payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        else:
            payload = build_news_risk_payload(news_items, portfolio)
        save_news_risk_payload(payload, target)
        if sync_dashboard:
            self._upload_news_risk_payload(payload)
        logger.info("News risks collected: %s", target)
        return payload

    def merge_news_risks(
        self,
        codex_path: Path,
        output_path: Path | None = None,
        sync_dashboard: bool = False,
    ) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        source = self._news_risk_output_path()
        target = Path(output_path) if output_path else source
        base_payload = load_json_object(source)
        codex_payload = load_json_object(Path(codex_path))
        _, portfolio = self._evaluate_current_portfolio()
        payload = merge_codex_news_risks(base_payload, codex_payload, portfolio)
        save_news_risk_payload(payload, target)
        if sync_dashboard:
            self._upload_news_risk_payload(payload)
        logger.info("Codex news risks merged: %s", target)
        return payload

    def sync_news_risks(self, path: Path) -> Dict[str, object]:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        payload = load_json_object(Path(path))
        validate_news_risk_payload(payload)
        self._upload_news_risk_payload(payload)
        logger.info("News risks synced: %s", path)
        return payload

    def _news_risk_output_path(self) -> Path:
        return Path(self.config.news.snapshot_path).parent / "news_risk_latest.json"

    def _upload_news_risk_payload(self, payload: Dict[str, object]) -> None:
        upload_dashboard_payload(
            payload,
            self.env.get("WATCHDOG_DASHBOARD_UPLOAD_URL"),
            self.env.get("WATCHDOG_UPLOAD_TOKEN"),
        )

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
