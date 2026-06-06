import sqlite3
from datetime import datetime

import pytest

from portfolio_watchdog.config import LedgerConfig, load_config
from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot, LedgerEvent
from portfolio_watchdog.ledger.repository import LedgerRepository


def _event(**overrides) -> LedgerEvent:
    values = {
        "provider": "upbit",
        "provider_event_id": "order-1",
        "occurred_at": datetime(2026, 6, 6, 8, 0),
        "event_type": "buy",
        "asset_symbol": "BTC",
        "cash_flow_krw": -100_000,
        "quantity": 0.001,
        "unit_price_krw": 100_000_000,
        "fee_krw": 500,
        "external_cash_flow": False,
        "memo": "private order detail",
    }
    values.update(overrides)
    return LedgerEvent(**values)


def test_ledger_repository_initializes_schema_and_connection_settings(tmp_path) -> None:
    path = tmp_path / "nested" / "watchdog.db"
    LedgerRepository(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "schema_version",
        "ledger_events",
        "account_snapshots",
        "asset_snapshots",
        "collection_cursors",
    } <= tables


def test_repository_closes_connections_after_transactions(tmp_path, monkeypatch) -> None:
    connections = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("portfolio_watchdog.ledger.repository.sqlite3.connect", tracking_connect)
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.upsert_event(_event())
    repository.list_events()

    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


def test_upsert_event_is_idempotent_and_updates_mutable_detail(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    original = _event()
    revised = _event(
        occurred_at=datetime(2026, 6, 6, 8, 1),
        cash_flow_krw=-101_000,
        quantity=0.00101,
        unit_price_krw=100_000_100,
        fee_krw=510,
        external_cash_flow=True,
        memo="revised private detail",
    )

    assert repository.upsert_event(original) is True
    assert repository.upsert_event(original) is False
    assert repository.upsert_event(revised) is False
    assert repository.list_events() == [revised]


def test_list_events_filters_restores_datetime_and_orders_ascending(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    later = _event(provider_event_id="later", occurred_at=datetime(2026, 6, 6, 10, 0))
    earlier = _event(provider_event_id="earlier", occurred_at=datetime(2026, 6, 6, 8, 0))
    middle = _event(provider_event_id="middle", occurred_at=datetime(2026, 6, 6, 9, 0))
    for event in (later, earlier, middle):
        repository.upsert_event(event)

    assert repository.list_events() == [earlier, middle, later]
    assert repository.list_events(since=middle.occurred_at, until=later.occurred_at) == [
        middle,
        later,
    ]


def test_ledger_repository_stores_sensitive_event_detail_locally(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    event = _event()

    repository.upsert_event(event)

    stored = repository.list_events()[0]
    assert stored.quantity == 0.001
    assert stored.unit_price_krw == 100_000_000
    assert stored.memo == "private order detail"


def test_account_snapshot_upsert_and_list(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    earlier = AccountSnapshot("upbit", datetime(2026, 6, 6, 8, 0), 100_000, "actual")
    revised = AccountSnapshot("upbit", datetime(2026, 6, 6, 8, 0), 110_000, "partial")
    later = AccountSnapshot("kis", datetime(2026, 6, 6, 9, 0), 200_000, "actual")

    assert repository.upsert_account_snapshot(earlier) is True
    assert repository.upsert_account_snapshot(revised) is False
    assert repository.upsert_account_snapshot(later) is True
    assert repository.list_account_snapshots() == [revised, later]
    assert repository.list_account_snapshots(since=later.captured_at) == [later]


def test_asset_snapshot_upsert_and_list(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    captured_at = datetime(2026, 6, 6, 8, 0)
    btc = AssetSnapshot(
        "upbit", captured_at, "BTC", "coin", 100_000, 0.001, 100_000_000, 90_000_000, "actual"
    )
    revised_btc = AssetSnapshot(
        "upbit", captured_at, "BTC", "coin", 105_000, 0.001, 105_000_000, 90_000_000, "actual"
    )
    eth = AssetSnapshot(
        "upbit", datetime(2026, 6, 6, 9, 0), "ETH", "coin", 50_000, None, None, None, "partial"
    )

    assert repository.upsert_asset_snapshot(btc) is True
    assert repository.upsert_asset_snapshot(revised_btc) is False
    assert repository.upsert_asset_snapshot(eth) is True
    assert repository.list_asset_snapshots() == [revised_btc, eth]
    assert repository.list_asset_snapshots(captured_at=captured_at) == [revised_btc]


def test_cursor_round_trip_and_update(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    assert repository.get_cursor("upbit", "orders") is None
    repository.set_cursor("upbit", "orders", "cursor-1", datetime(2026, 6, 6, 8, 0))
    repository.set_cursor("upbit", "orders", "cursor-2", datetime(2026, 6, 6, 9, 0))

    assert repository.get_cursor("upbit", "orders") == "cursor-2"


def test_ledger_config_defaults_and_top_level_parsing(tmp_path) -> None:
    assert LedgerConfig() == LedgerConfig(
        path="snapshots/watchdog.db",
        reconciliation_quantity_tolerance=1e-8,
        raw_response_retention_days=30,
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
portfolio:
  assets:
    - symbol: BTC
      name: Bitcoin
ledger:
  path: private/ledger.db
  reconciliation_quantity_tolerance: 0.0001
  raw_response_retention_days: 7
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.ledger == LedgerConfig(
        path="private/ledger.db",
        reconciliation_quantity_tolerance=0.0001,
        raw_response_retention_days=7,
    )
