import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from portfolio_watchdog.config import LedgerConfig, load_config
from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot, LedgerEvent
from portfolio_watchdog.ledger.repository import BUSY_TIMEOUT_MS, LedgerRepository
from portfolio_watchdog.ledger.schema import SCHEMA_STATEMENTS, SCHEMA_VERSION


UTC = timezone.utc


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _call_concurrently(function, value):
    barrier = Barrier(2)

    def call(_):
        barrier.wait()
        return function(value)

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(call, range(2)))


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
    repository = LedgerRepository(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [
            (SCHEMA_VERSION,)
        ]
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
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

    with repository._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
            )


def test_connection_sets_busy_timeout_before_journal_mode(tmp_path, monkeypatch) -> None:
    statements = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr("portfolio_watchdog.ledger.repository.sqlite3.connect", tracking_connect)

    LedgerRepository(tmp_path / "watchdog.db")

    busy_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.upper().startswith("PRAGMA BUSY_TIMEOUT")
    )
    journal_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.upper().startswith("PRAGMA JOURNAL_MODE")
    )
    assert busy_index < journal_index


def test_concurrent_first_initialization_does_not_lock_database(tmp_path) -> None:
    path = tmp_path / "watchdog.db"
    barrier = Barrier(8)

    def initialize(_):
        barrier.wait()
        return LedgerRepository(path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        repositories = list(executor.map(initialize, range(8)))

    assert len(repositories) == 8
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [
            (SCHEMA_VERSION,)
        ]


def test_schema_initialization_rolls_back_on_failure(tmp_path, monkeypatch) -> None:
    path = tmp_path / "watchdog.db"
    monkeypatch.setattr(
        "portfolio_watchdog.ledger.repository.SCHEMA_STATEMENTS",
        (*SCHEMA_STATEMENTS, "CREATE TABLE broken("),
    )

    with pytest.raises(sqlite3.OperationalError):
        LedgerRepository(path)

    with sqlite3.connect(path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    assert tables == []


@pytest.mark.parametrize("versions", [[0], [SCHEMA_VERSION + 1], [SCHEMA_VERSION, SCHEMA_VERSION]])
def test_schema_initialization_rejects_invalid_version_rows(tmp_path, versions) -> None:
    path = tmp_path / "watchdog.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
        connection.executemany(
            "INSERT INTO schema_version(version) VALUES (?)",
            [(version,) for version in versions],
        )

    with pytest.raises(RuntimeError, match="schema version"):
        LedgerRepository(path)


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
    assert repository.list_events() == [
        LedgerEvent(**{**revised.__dict__, "occurred_at": _utc(revised.occurred_at)})
    ]


@pytest.mark.parametrize(
    "stale",
    [
        _event(quantity=0.0009, cash_flow_krw=-110_000, fee_krw=600),
        _event(quantity=0.002, cash_flow_krw=-90_000, fee_krw=600),
        _event(quantity=0.002, cash_flow_krw=-110_000, fee_krw=400),
        _event(quantity=None, cash_flow_krw=-110_000, fee_krw=600),
    ],
)
def test_upsert_event_does_not_replace_cumulative_values_with_stale_data(
    tmp_path, stale
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    current = _event(quantity=0.001, cash_flow_krw=-100_000, fee_krw=500)

    repository.upsert_event(current)
    assert repository.upsert_event(stale) is False

    assert repository.list_events() == [
        LedgerEvent(**{**current.__dict__, "occurred_at": _utc(current.occurred_at)})
    ]


def test_upsert_event_accepts_equal_or_increased_cumulative_values(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    current = _event(quantity=0.001, cash_flow_krw=-100_000, fee_krw=500)
    increased = _event(
        occurred_at=datetime(2026, 6, 6, 8, 1),
        quantity=0.002,
        cash_flow_krw=-110_000,
        fee_krw=600,
        memo="latest cumulative detail",
    )

    repository.upsert_event(current)
    assert repository.upsert_event(increased) is False

    assert repository.list_events() == [
        LedgerEvent(**{**increased.__dict__, "occurred_at": _utc(increased.occurred_at)})
    ]


def test_concurrent_event_upsert_returns_true_exactly_once(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    event = _event()

    results = _call_concurrently(repository.upsert_event, event)

    assert sorted(results) == [False, True]
    assert len(repository.list_events()) == 1


def test_list_events_filters_restores_datetime_and_orders_ascending(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    later = _event(provider_event_id="later", occurred_at=datetime(2026, 6, 6, 10, 0))
    earlier = _event(provider_event_id="earlier", occurred_at=datetime(2026, 6, 6, 8, 0))
    middle = _event(provider_event_id="middle", occurred_at=datetime(2026, 6, 6, 9, 0))
    for event in (later, earlier, middle):
        repository.upsert_event(event)

    assert repository.list_events() == [
        LedgerEvent(**{**event.__dict__, "occurred_at": _utc(event.occurred_at)})
        for event in (earlier, middle, later)
    ]
    assert repository.list_events(since=middle.occurred_at, until=later.occurred_at) == [
        LedgerEvent(**{**event.__dict__, "occurred_at": _utc(event.occurred_at)})
        for event in (middle, later)
    ]


def test_event_datetimes_are_normalized_to_utc_for_storage_sorting_and_filters(tmp_path) -> None:
    path = tmp_path / "watchdog.db"
    repository = LedgerRepository(path)
    same_instant_offset = _event(
        provider_event_id="same-offset",
        occurred_at=datetime(2026, 6, 6, 17, 0, tzinfo=timezone(timedelta(hours=9))),
    )
    same_instant_naive = _event(
        provider_event_id="same-naive",
        occurred_at=datetime(2026, 6, 6, 8, 0),
    )
    later = _event(
        provider_event_id="later",
        occurred_at=datetime(2026, 6, 6, 5, 30, tzinfo=timezone(timedelta(hours=-3))),
    )
    for event in (later, same_instant_offset, same_instant_naive):
        repository.upsert_event(event)

    events = repository.list_events(
        since=datetime(2026, 6, 6, 16, 59, tzinfo=timezone(timedelta(hours=9)))
    )

    assert [event.provider_event_id for event in events] == [
        "same-offset",
        "same-naive",
        "later",
    ]
    assert [event.occurred_at for event in events] == [
        datetime(2026, 6, 6, 8, 0, tzinfo=UTC),
        datetime(2026, 6, 6, 8, 0, tzinfo=UTC),
        datetime(2026, 6, 6, 8, 30, tzinfo=UTC),
    ]
    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT occurred_at FROM ledger_events ORDER BY occurred_at, id"
        ).fetchall()
    assert stored == [
        ("2026-06-06T08:00:00+00:00",),
        ("2026-06-06T08:00:00+00:00",),
        ("2026-06-06T08:30:00+00:00",),
    ]


def test_naive_stored_datetime_is_restored_as_utc(tmp_path) -> None:
    path = tmp_path / "watchdog.db"
    repository = LedgerRepository(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO ledger_events(
                provider, provider_event_id, occurred_at, event_type, asset_symbol,
                cash_flow_krw, quantity, unit_price_krw, fee_krw, external_cash_flow, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upbit",
                "legacy-naive",
                "2026-06-06T08:00:00",
                "buy",
                "BTC",
                -100_000,
                0.001,
                100_000_000,
                500,
                0,
                None,
            ),
        )

    assert repository.list_events()[0].occurred_at == datetime(
        2026, 6, 6, 8, 0, tzinfo=UTC
    )


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
    assert repository.list_account_snapshots() == [
        AccountSnapshot(**{**snapshot.__dict__, "captured_at": _utc(snapshot.captured_at)})
        for snapshot in (revised, later)
    ]
    assert repository.list_account_snapshots(since=later.captured_at) == [
        AccountSnapshot(**{**later.__dict__, "captured_at": _utc(later.captured_at)})
    ]


def test_concurrent_account_snapshot_upsert_returns_true_exactly_once(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    snapshot = AccountSnapshot("upbit", datetime(2026, 6, 6, 8, 0), 100_000, "actual")

    results = _call_concurrently(repository.upsert_account_snapshot, snapshot)

    assert sorted(results) == [False, True]
    assert len(repository.list_account_snapshots()) == 1


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
    assert repository.list_asset_snapshots() == [
        AssetSnapshot(**{**snapshot.__dict__, "captured_at": _utc(snapshot.captured_at)})
        for snapshot in (revised_btc, eth)
    ]
    assert repository.list_asset_snapshots(captured_at=captured_at) == [
        AssetSnapshot(**{**revised_btc.__dict__, "captured_at": _utc(captured_at)})
    ]


def test_concurrent_asset_snapshot_upsert_returns_true_exactly_once(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    snapshot = AssetSnapshot(
        "upbit",
        datetime(2026, 6, 6, 8, 0),
        "BTC",
        "coin",
        100_000,
        0.001,
        100_000_000,
        90_000_000,
        "actual",
    )

    results = _call_concurrently(repository.upsert_asset_snapshot, snapshot)

    assert sorted(results) == [False, True]
    assert len(repository.list_asset_snapshots()) == 1


def test_snapshot_same_instant_with_different_offsets_is_one_unique_row(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    utc_snapshot = AccountSnapshot(
        "upbit", datetime(2026, 6, 6, 8, 0, tzinfo=UTC), 100_000, "actual"
    )
    offset_snapshot = AccountSnapshot(
        "upbit",
        datetime(2026, 6, 6, 17, 0, tzinfo=timezone(timedelta(hours=9))),
        110_000,
        "partial",
    )

    assert repository.upsert_account_snapshot(utc_snapshot) is True
    assert repository.upsert_account_snapshot(offset_snapshot) is False
    assert repository.list_account_snapshots() == [
        AccountSnapshot("upbit", datetime(2026, 6, 6, 8, 0, tzinfo=UTC), 110_000, "partial")
    ]


def test_cursor_round_trip_and_update(tmp_path) -> None:
    path = tmp_path / "watchdog.db"
    repository = LedgerRepository(path)

    assert repository.get_cursor("upbit", "orders") is None
    repository.set_cursor("upbit", "orders", "cursor-1", datetime(2026, 6, 6, 8, 0))
    repository.set_cursor("upbit", "orders", "cursor-2", datetime(2026, 6, 6, 9, 0))

    assert repository.get_cursor("upbit", "orders") == "cursor-2"
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT updated_at FROM collection_cursors WHERE provider = 'upbit' AND stream = 'orders'"
        ).fetchone() == ("2026-06-06T09:00:00+00:00",)


def test_cursor_does_not_move_backward_for_iso_datetime(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor(
        "upbit", "trades", "2026-06-06T09:00:00+09:00", datetime(2026, 6, 6, 1, 0)
    )
    repository.set_cursor(
        "upbit", "trades", "2026-06-05T23:00:00+00:00", datetime(2026, 6, 6, 2, 0)
    )

    assert repository.get_cursor("upbit", "trades") == "2026-06-06T09:00:00+09:00"


def test_cursor_does_not_move_backward_for_numeric_pagination_cursor(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor("kis", "orders", "10", datetime(2026, 6, 6, 1, 0))
    repository.set_cursor("kis", "orders", "9", datetime(2026, 6, 6, 2, 0))
    assert repository.get_cursor("kis", "orders") == "10"

    repository.set_cursor("kis", "orders", "11", datetime(2026, 6, 6, 3, 0))
    assert repository.get_cursor("kis", "orders") == "11"


def test_opaque_cursor_order_is_owned_by_caller(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor("provider", "opaque", "cursor-z", datetime(2026, 6, 6, 1, 0))
    repository.set_cursor("provider", "opaque", "cursor-a", datetime(2026, 6, 6, 2, 0))

    assert repository.get_cursor("provider", "opaque") == "cursor-a"


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
