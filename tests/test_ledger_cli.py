import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import portfolio_watchdog.app as app_module
import portfolio_watchdog.cli as cli_module
from portfolio_watchdog.app import PortfolioWatchdogApp
from portfolio_watchdog.config import (
    AlertConfig,
    AppConfig,
    AssetConfig,
    LedgerConfig,
    NewsConfig,
    PortfolioProviderConfig,
    PriceProviderConfig,
    SnapshotConfig,
    TelegramConfig,
)
from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot
from portfolio_watchdog.providers.config_portfolio_provider import ConfigPortfolioProvider
from portfolio_watchdog.providers.kis import KisPortfolioProvider
from portfolio_watchdog.providers.upbit import UpbitPortfolioProvider
from portfolio_watchdog.runtime_paths import RuntimePaths


UTC = timezone.utc


def test_build_parser_keeps_existing_commands_and_adds_ledger_commands() -> None:
    parser = cli_module.build_parser()

    assert parser.parse_args(["run"]).command == "run"
    assert parser.parse_args(["sync-ledger"]).command == "sync-ledger"
    assert parser.parse_args(["sync-ledger", "--sync-dashboard"]).sync_dashboard is True
    assert parser.parse_args(["refresh-dashboard"]).command == "refresh-dashboard"
    assert parser.parse_args(["refresh-dashboard", "--skip-codex"]).skip_codex is True
    assert parser.parse_args(["prepare-codex-inputs"]).command == "prepare-codex-inputs"
    assert parser.parse_args(["performance-summary"]).command == "performance-summary"
    args = parser.parse_args(
        [
            "add-cash-flow",
            "--amount",
            "-1250.5",
            "--occurred-at",
            "2026-06-10T12:30:00",
            "--memo",
            "monthly transfer",
        ]
    )
    assert args.amount == -1250.5
    assert args.occurred_at == "2026-06-10T12:30:00"
    assert args.memo == "monthly transfer"


@pytest.mark.parametrize(
    ("argv", "method", "expected_args"),
    [
        (["sync-ledger"], "sync_ledger", ()),
        (["performance-summary"], "performance_summary", ()),
        (
            [
                "add-cash-flow",
                "--amount",
                "1000",
                "--occurred-at",
                "2026-06-10T12:30:00",
                "--memo",
                "deposit",
            ],
            "add_cash_flow",
            (1000.0, datetime(2026, 6, 10, 12, 30, tzinfo=UTC), "deposit"),
        ),
    ],
)
def test_main_routes_ledger_commands_and_treats_naive_cash_flow_time_as_utc(
    monkeypatch, tmp_path, argv, method, expected_args
) -> None:
    calls = []

    class FakeApp:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def sync_ledger(self):
            calls.append(("sync_ledger", ()))

        def performance_summary(self):
            calls.append(("performance_summary", ()))

        def add_cash_flow(self, *args):
            calls.append(("add_cash_flow", args))

    _patch_cli_runtime(monkeypatch, tmp_path, FakeApp)
    monkeypatch.setattr(sys, "argv", ["portfolio-watchdog", *argv])

    cli_module.main()

    assert calls[-1] == (method, expected_args)


def test_main_converts_new_command_errors_to_system_exit_one(
    monkeypatch, tmp_path
) -> None:
    class FakeApp:
        def __init__(self, **kwargs):
            pass

        def sync_ledger(self):
            raise RuntimeError("sync failed")

    _patch_cli_runtime(monkeypatch, tmp_path, FakeApp)
    monkeypatch.setattr(sys, "argv", ["portfolio-watchdog", "sync-ledger"])

    with pytest.raises(SystemExit) as raised:
        cli_module.main()

    assert raised.value.code == 1


def test_main_routes_sync_ledger_dashboard_option(monkeypatch, tmp_path) -> None:
    calls = []

    class FakeApp:
        def __init__(self, **kwargs):
            pass

        def sync_ledger(self, sync_dashboard=False):
            calls.append(sync_dashboard)
            return {"schema_version": "dashboard_payload_v2"}

    _patch_cli_runtime(monkeypatch, tmp_path, FakeApp)
    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio-watchdog", "sync-ledger", "--sync-dashboard"],
    )

    cli_module.main()

    assert calls == [True]


def test_main_routes_dashboard_automation_commands(monkeypatch, tmp_path) -> None:
    calls = []

    class FakeApp:
        def __init__(self, **kwargs):
            pass

        def refresh_dashboard(self, sync_codex=True):
            calls.append(("refresh_dashboard", sync_codex))
            return {"schema_version": "dashboard_refresh_v1"}

        def prepare_codex_inputs(self):
            calls.append(("prepare_codex_inputs", None))
            return {"schema_version": "codex_dashboard_inputs_v1"}

    _patch_cli_runtime(monkeypatch, tmp_path, FakeApp)
    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio-watchdog", "refresh-dashboard", "--skip-codex"],
    )

    cli_module.main()

    monkeypatch.setattr(sys, "argv", ["portfolio-watchdog", "prepare-codex-inputs"])

    cli_module.main()

    assert calls == [
        ("refresh_dashboard", False),
        ("prepare_codex_inputs", None),
    ]


def test_main_routes_run_dashboard_loop(monkeypatch, tmp_path) -> None:
    calls = []

    class FakeApp:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

    def fake_loop(app, *, interval_seconds, once):
        calls.append(("run_dashboard_loop", app.__class__.__name__, interval_seconds, once))
        return {"executed": []}

    _patch_cli_runtime(monkeypatch, tmp_path, FakeApp)
    monkeypatch.setattr(cli_module, "run_dashboard_loop", fake_loop)
    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio-watchdog", "run-dashboard-loop", "--interval-seconds", "30", "--once"],
    )

    cli_module.main()

    assert calls[-1] == ("run_dashboard_loop", "FakeApp", 30, True)


def test_add_cash_flow_is_deterministically_idempotent(tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    occurred_at = datetime(2026, 6, 10, 12, 30)

    assert watchdog.add_cash_flow(1000, occurred_at, "deposit") is True
    assert watchdog.add_cash_flow(1000, occurred_at, "deposit") is False

    events = watchdog.ledger_repository.list_events()
    assert len(events) == 1
    assert events[0].occurred_at == datetime(2026, 6, 10, 12, 30, tzinfo=UTC)
    assert events[0].external_cash_flow is True


def test_sync_ledger_collects_in_order_writes_v2_and_performance_summary_is_offline(
    monkeypatch, tmp_path
) -> None:
    config = _app_config(tmp_path)
    config.snapshot.history_path = str(tmp_path / "history.json")
    Path(config.snapshot.history_path).write_text(
        json.dumps({"portfolio_snapshots": [], "news_items": []}),
        encoding="utf-8",
    )
    watchdog = PortfolioWatchdogApp(config, env={})
    calls = []
    now = datetime(2026, 6, 12, 3, 0, tzinfo=UTC)

    class UpbitClient:
        def get_accounts(self):
            calls.append("upbit-balance")
            return [{"currency": "BTC", "balance": "0.01", "avg_buy_price": "90000"}]

    class KisClient:
        def get_balance(self):
            calls.append("kis-balance")
            return []

        def get_daily_executions(self, start_date, end_date):
            calls.append(("kis-executions", start_date, end_date))
            return []

    base = ConfigPortfolioProvider(config)
    upbit_client = UpbitClient()
    kis_client = KisClient()
    watchdog.portfolio_provider = KisPortfolioProvider(
        UpbitPortfolioProvider(config, upbit_client, False, base),
        kis_client,
        False,
    )

    monkeypatch.setattr(app_module, "_utc_now", lambda: now)
    monkeypatch.setattr(
        app_module,
        "import_history_json",
        lambda path, repository: calls.append("legacy") or 0,
    )
    monkeypatch.setattr(
        app_module,
        "fetch_upbit_closed_orders",
        lambda client, start, end: calls.append("upbit-orders") or [],
    )
    monkeypatch.setattr(
        app_module,
        "fetch_upbit_deposits",
        lambda client: calls.append("upbit-deposits") or [],
    )
    monkeypatch.setattr(
        app_module,
        "fetch_upbit_withdraws",
        lambda client: calls.append("upbit-withdraws") or [],
    )
    monkeypatch.setattr(
        app_module,
        "parse_upbit_closed_orders",
        lambda rows: calls.append("parse-upbit-orders") or [],
    )
    monkeypatch.setattr(
        app_module,
        "parse_upbit_deposits",
        lambda rows: calls.append("parse-upbit-deposits") or [],
    )
    monkeypatch.setattr(
        app_module,
        "parse_upbit_withdraws",
        lambda rows: calls.append("parse-upbit-withdraws") or [],
    )
    monkeypatch.setattr(
        app_module,
        "parse_kis_daily_executions",
        lambda rows, mapping: calls.append(("parse-kis", mapping)) or [],
    )
    monkeypatch.setattr(
        app_module,
        "upload_dashboard_payload",
        lambda *args, **kwargs: pytest.fail("v1 dashboard upload called"),
    )

    def reconcile_after_snapshot(repository, previous_account, assets, captured_at):
        portfolio_snapshots = [
            snapshot
            for snapshot in repository.list_account_snapshots()
            if snapshot.provider == "portfolio"
        ]
        assert portfolio_snapshots[-1].captured_at == captured_at
        calls.append("reconcile")
        return app_module.ReconciliationResult("reconciled", {}, 1e-8)

    monkeypatch.setattr(
        watchdog, "_reconcile_current_quantities", reconcile_after_snapshot
    )

    payload = watchdog.sync_ledger()

    assert calls[:9] == [
        "legacy",
        "upbit-orders",
        "parse-upbit-orders",
        "upbit-deposits",
        "parse-upbit-deposits",
        "upbit-withdraws",
        "parse-upbit-withdraws",
        ("kis-executions", "20260605", "20260612"),
        ("parse-kis", {}),
    ]
    assert calls[9:] == ["upbit-balance", "kis-balance", "reconcile"]
    assert payload["schema_version"] == "dashboard_payload_v2"
    assert payload["generated_at"] == "2026-06-12T03:00:00+00:00"
    assert payload["data_freshness"]["portfolio_status"] == "actual"
    assert (tmp_path / "dashboard_v2_latest.json").exists()
    assert watchdog.ledger_repository.get_cursor("upbit", "closed_orders") == now.isoformat()
    assert watchdog.ledger_repository.get_cursor("kis", "daily_executions") == now.isoformat()
    assert {
        weight.asset_group
        for weight in watchdog.ledger_repository.get_target_allocation(
            now.astimezone(app_module.KST).date()
        )
    } == {"coin", "isa", "cash"}

    monkeypatch.setattr(
        watchdog,
        "_evaluate_current_portfolio",
        lambda: pytest.fail("performance_summary called an API"),
    )
    summary = watchdog.performance_summary()

    assert summary["performance"]["status"] == "insufficient_data"
    assert summary["total_value_krw"] == payload["total_value_krw"]


def test_sync_ledger_optionally_uploads_v2_payload(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={
        "WATCHDOG_DASHBOARD_UPLOAD_URL": "https://example.com/api/upload",
        "WATCHDOG_UPLOAD_TOKEN": "token",
    })
    uploaded = []
    payload = {"schema_version": "dashboard_payload_v2"}

    monkeypatch.setattr(
        watchdog,
        "_sync_ledger_payload",
        lambda: payload,
        raising=False,
    )
    monkeypatch.setattr(
        app_module,
        "upload_dashboard_payload",
        lambda value, endpoint, token: uploaded.append((value, endpoint, token)),
    )

    result = watchdog.sync_ledger(sync_dashboard=True)

    assert result == payload
    assert uploaded == [
        (payload, "https://example.com/api/upload", "token"),
    ]


def test_performance_summary_reconciles_latest_snapshots_without_api(
    monkeypatch, tmp_path
) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    repository = watchdog.ledger_repository
    earlier = datetime(2026, 6, 10, tzinfo=UTC)
    latest = datetime(2026, 6, 11, tzinfo=UTC)
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", earlier, 1000, "actual"),
        [AssetSnapshot("portfolio", earlier, "BTC", "coin", 1000, 1.0, 1000, 900, "actual")],
    )
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", latest, 1000, "actual"),
        [AssetSnapshot("portfolio", latest, "BTC", "coin", 1000, 1.5, 1000, 900, "actual")],
    )
    monkeypatch.setattr(app_module, "_utc_now", lambda: datetime(2026, 6, 12, tzinfo=UTC))
    monkeypatch.setattr(
        watchdog,
        "_evaluate_current_portfolio",
        lambda: pytest.fail("performance_summary called an API"),
    )

    summary = watchdog.performance_summary()

    assert summary["data_freshness"]["reconciliation_status"] == "reconciliation_required"
    assert summary["performance"]["status"] == "provisional"


def test_fallback_last_actual_at_includes_imported_legacy_snapshot() -> None:
    captured_at = datetime(2026, 6, 9, tzinfo=UTC)

    assert app_module._latest_actual_at(
        [AccountSnapshot("legacy_history", captured_at, 1000, "actual")]
    ) == captured_at


def test_latest_portfolio_account_ignores_fallback_snapshot() -> None:
    actual = AccountSnapshot(
        "portfolio", datetime(2026, 6, 10, tzinfo=UTC), 1000, "actual"
    )
    fallback = AccountSnapshot(
        "portfolio", datetime(2026, 6, 11, tzinfo=UTC), 900, "fallback"
    )

    assert app_module._latest_portfolio_account([actual, fallback]) == actual


def test_reconcile_stored_quantities_detects_disappeared_asset(tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    repository = watchdog.ledger_repository
    earlier = datetime(2026, 6, 10, tzinfo=UTC)
    latest = datetime(2026, 6, 11, tzinfo=UTC)
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", earlier, 1000, "actual"),
        [AssetSnapshot("portfolio", earlier, "BTC", "coin", 1000, 1.0, 1000, 900, "actual")],
    )
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", latest, 1000, "actual"),
        [],
    )

    result = app_module._reconcile_stored_portfolio_quantities(
        repository,
        repository.list_account_snapshots(),
        1e-8,
    )

    assert result.status == "reconciliation_required"
    assert result.differences == {"BTC": -1.0}


def test_sync_kis_recollects_overlap_for_late_execution(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    repository = watchdog.ledger_repository
    now = datetime(2026, 6, 12, 3, tzinfo=UTC)
    repository.set_cursor(
        "kis", "daily_executions", datetime(2026, 6, 12, tzinfo=UTC).isoformat(), now
    )
    late = app_module.LedgerEvent(
        provider="kis",
        provider_event_id="late",
        occurred_at=datetime(2026, 6, 11, tzinfo=UTC),
        event_type="buy",
        asset_symbol="BTC",
        cash_flow_krw=-100,
        quantity=1,
    )

    class Client:
        def get_daily_executions(self, start_date, end_date):
            assert start_date == "20260605"
            return [{}]

    monkeypatch.setattr(
        app_module, "parse_kis_daily_executions", lambda rows, mapping: [late]
    )

    watchdog._sync_kis_events(repository, Client(), now)

    assert repository.list_events() == [late]


def test_performance_summary_marks_unbounded_cash_flow_interval_provisional(
    monkeypatch, tmp_path
) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    repository = watchdog.ledger_repository
    earlier = datetime(2026, 6, 10, tzinfo=UTC)
    latest = datetime(2026, 6, 11, tzinfo=UTC)
    snapshot = AssetSnapshot(
        "portfolio", earlier, "BTC", "coin", 1000, 1.0, 1000, 900, "actual"
    )
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", earlier, 1000, "actual"), [snapshot]
    )
    repository.upsert_snapshot(
        AccountSnapshot("portfolio", latest, 1100, "actual"),
        [AssetSnapshot(**{**snapshot.__dict__, "captured_at": latest, "value_krw": 1100})],
    )
    watchdog.add_cash_flow(
        100,
        datetime(2026, 6, 10, 12, tzinfo=UTC),
        "deposit without boundary snapshots",
    )
    monkeypatch.setattr(
        app_module, "_utc_now", lambda: datetime(2026, 6, 12, tzinfo=UTC)
    )

    summary = watchdog.performance_summary()

    assert summary["performance"]["status"] == "provisional"


def test_target_allocation_same_kst_date_conflict_does_not_break_sync(tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    repository = watchdog.ledger_repository
    now = datetime(2026, 6, 10, 16, tzinfo=UTC)

    watchdog._save_target_allocation(repository, now)
    watchdog.config.assets[0].target_weight = 0.4
    watchdog.config.assets[1].target_weight = 0.6
    watchdog._save_target_allocation(repository, now + app_module.timedelta(hours=1))

    weights = repository.get_target_allocation(
        now.astimezone(app_module.KST).date()
    )
    assert {weight.asset_group: weight.weight for weight in weights} == {
        "coin": 0.5,
        "isa": 0.0,
        "cash": 0.5,
    }


def _patch_cli_runtime(monkeypatch, tmp_path, app_class) -> None:
    paths = RuntimePaths(
        config_path=tmp_path / "config.yaml",
        env_path=tmp_path / ".env",
        settings_root=tmp_path,
    )
    monkeypatch.setattr(cli_module, "resolve_runtime_paths", lambda *args: paths)
    monkeypatch.setattr(cli_module, "load_env", lambda path: {})
    monkeypatch.setattr(cli_module, "load_config", lambda path: _app_config(tmp_path))
    monkeypatch.setattr(cli_module, "PortfolioWatchdogApp", app_class)


def _app_config(tmp_path) -> AppConfig:
    return AppConfig(
        assets=[
            AssetConfig(
                symbol="BTC",
                name="Bitcoin",
                asset_type="coin",
                target_weight=0.5,
                current_quantity=0.01,
            ),
            AssetConfig(
                symbol="CASH",
                name="Cash",
                asset_type="cash",
                target_weight=0.5,
                manual_value_krw=1000,
            ),
        ],
        portfolio_provider=PortfolioProviderConfig(),
        price_provider=PriceProviderConfig(
            provider_type="mock", fallback_prices={"BTC": 100_000}
        ),
        alert_settings=AlertConfig(),
        telegram=TelegramConfig(enabled=False),
        snapshot=SnapshotConfig(
            path=str(tmp_path / "state.json"),
            history_path=str(tmp_path / "history.json"),
        ),
        news=NewsConfig(provider_type="noop"),
        ledger=LedgerConfig(path=str(tmp_path / "watchdog.db")),
    )
