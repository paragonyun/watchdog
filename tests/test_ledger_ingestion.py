import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from portfolio_watchdog.ledger.ingestion import (
    ProviderPage,
    add_manual_cash_flow,
    ingest_provider_events,
)
from portfolio_watchdog.ledger.models import LedgerEvent
from portfolio_watchdog.ledger.repository import LedgerRepository


UTC = timezone.utc


def _event(provider_event_id: str, provider: str = "upbit") -> LedgerEvent:
    return LedgerEvent(
        provider=provider,
        provider_event_id=provider_event_id,
        occurred_at=datetime(2026, 6, 7, 1, 0),
        event_type="buy",
        asset_symbol="BTC",
        cash_flow_krw=-100_000,
        quantity=0.001,
        unit_price_krw=100_000_000,
        fee_krw=500,
        external_cash_flow=False,
        memo=None,
    )


def test_add_manual_cash_flow_stores_deposit_and_withdrawal_locally(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    assert add_manual_cash_flow(
        repository,
        datetime(2026, 6, 7, 10, 0, tzinfo=timezone(timedelta(hours=9))),
        1_000_000,
        "salary",
        "manual-1",
    )
    assert add_manual_cash_flow(
        repository,
        datetime(2026, 6, 7, 2, 0),
        -200_000,
        "living cost",
        "manual-2",
    )

    assert repository.list_events() == [
        LedgerEvent(
            provider="manual",
            provider_event_id="manual-1",
            occurred_at=datetime(2026, 6, 7, 1, 0, tzinfo=UTC),
            event_type="deposit",
            asset_symbol=None,
            cash_flow_krw=1_000_000,
            quantity=None,
            unit_price_krw=None,
            fee_krw=0,
            external_cash_flow=True,
            memo="salary",
        ),
        LedgerEvent(
            provider="manual",
            provider_event_id="manual-2",
            occurred_at=datetime(2026, 6, 7, 2, 0, tzinfo=UTC),
            event_type="withdrawal",
            asset_symbol=None,
            cash_flow_krw=-200_000,
            quantity=None,
            unit_price_krw=None,
            fee_krw=0,
            external_cash_flow=True,
            memo="living cost",
        ),
    ]


def test_add_manual_cash_flow_is_idempotent(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    arguments = (
        repository,
        datetime(2026, 6, 7, 1, 0),
        1_000,
        "transfer",
        "manual-1",
    )

    assert add_manual_cash_flow(*arguments) is True
    assert add_manual_cash_flow(*arguments) is False
    assert len(repository.list_events()) == 1


def test_add_manual_cash_flow_rejects_idempotency_conflict_and_preserves_original(
    tmp_path,
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    original = (
        repository,
        datetime(2026, 6, 7, 1, 0),
        1_000,
        "transfer",
        "manual-1",
    )
    add_manual_cash_flow(*original)

    with pytest.raises(ValueError, match="manual cash flow idempotency conflict"):
        add_manual_cash_flow(
            repository,
            datetime(2026, 6, 7, 2, 0),
            -1_000,
            "different transfer",
            "manual-1",
        )

    assert repository.list_events() == [
        LedgerEvent(
            provider="manual",
            provider_event_id="manual-1",
            occurred_at=datetime(2026, 6, 7, 1, 0, tzinfo=UTC),
            event_type="deposit",
            asset_symbol=None,
            cash_flow_krw=1_000,
            quantity=None,
            unit_price_krw=None,
            fee_krw=0,
            external_cash_flow=True,
            memo="transfer",
        )
    ]


@pytest.mark.parametrize("amount", [0, float("nan"), float("inf"), float("-inf")])
def test_add_manual_cash_flow_rejects_zero_or_non_finite_amount(tmp_path, amount) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    with pytest.raises(ValueError, match="amount_krw"):
        add_manual_cash_flow(repository, datetime(2026, 6, 7), amount, "memo", "key")

    assert repository.list_events() == []


@pytest.mark.parametrize(
    ("memo", "idempotency_key", "field"),
    [
        ("memo", "", "idempotency_key"),
        ("memo", "   ", "idempotency_key"),
        ("memo", None, "idempotency_key"),
        ("", "key", "memo"),
        ("   ", "key", "memo"),
        (None, "key", "memo"),
    ],
)
def test_add_manual_cash_flow_rejects_invalid_key_or_memo(
    tmp_path, memo, idempotency_key, field
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    with pytest.raises(ValueError, match=field):
        add_manual_cash_flow(
            repository, datetime(2026, 6, 7), 1_000, memo, idempotency_key
        )

    assert repository.list_events() == []


def test_ingest_provider_events_stores_two_pages_and_resumes_idempotently(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    calls = []

    def fetch_page(cursor):
        calls.append(cursor)
        if cursor is None:
            return ProviderPage(
                [_event("1")], "page-2", "checkpoint-1", datetime(2026, 6, 7, 1)
            )
        if cursor == "page-2":
            return ProviderPage(
                [_event("2")], None, "checkpoint-2", datetime(2026, 6, 7, 2)
            )
        assert cursor == "checkpoint-2"
        return ProviderPage([], None, "checkpoint-2", datetime(2026, 6, 7, 3))

    assert ingest_provider_events(repository, "upbit", "orders", fetch_page) == 2
    assert calls == [None, "page-2"]
    assert repository.get_cursor("upbit", "orders") == "checkpoint-2"
    assert [event.provider_event_id for event in repository.list_events()] == ["1", "2"]

    calls.clear()
    assert ingest_provider_events(repository, "upbit", "orders", fetch_page) == 0
    assert calls == ["checkpoint-2"]
    assert [event.provider_event_id for event in repository.list_events()] == ["1", "2"]


def test_ingest_provider_events_rolls_back_page_and_cursor_on_database_failure(
    tmp_path,
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor("upbit", "orders", "before", datetime(2026, 6, 7, 0))
    with repository._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_page_insert
            BEFORE INSERT ON ledger_events
            WHEN NEW.provider_event_id = 'bad'
            BEGIN
                SELECT RAISE(ABORT, 'forced page failure');
            END
            """
        )

    def fetch_page(cursor):
        assert cursor == "before"
        return ProviderPage(
            [_event("good"), _event("bad")],
            None,
            "after",
            datetime(2026, 6, 7, 1),
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced page failure"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)

    assert repository.list_events() == []
    assert repository.get_cursor("upbit", "orders") == "before"


def test_ingest_provider_events_propagates_fetch_failure_without_advancing_cursor(
    tmp_path,
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor("upbit", "orders", "before", datetime(2026, 6, 7, 0))

    def fetch_page(cursor):
        assert cursor == "before"
        raise ConnectionError("provider unavailable")

    with pytest.raises(ConnectionError, match="provider unavailable"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)

    assert repository.get_cursor("upbit", "orders") == "before"


def test_ingest_provider_events_rejects_repeated_cursor(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    def fetch_page(cursor):
        return ProviderPage([], "same", "checkpoint", datetime(2026, 6, 7, 1))

    with pytest.raises(RuntimeError, match="repeated next_page_cursor"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)


def test_ingest_provider_events_rejects_excessive_pages(tmp_path, monkeypatch) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    calls = []
    monkeypatch.setattr("portfolio_watchdog.ledger.ingestion.MAX_PAGES", 2)

    def fetch_page(cursor):
        calls.append(cursor)
        return ProviderPage(
            [], f"cursor-{len(calls)}", f"checkpoint-{len(calls)}", datetime(2026, 6, 7, 1)
        )

    with pytest.raises(RuntimeError, match="page limit"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)

    assert calls == [None, "cursor-1"]


def test_ingest_provider_events_rejects_provider_mismatch_without_storing_page(
    tmp_path,
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    def fetch_page(cursor):
        return ProviderPage(
            [_event("1", provider="kis")],
            None,
            "checkpoint",
            datetime(2026, 6, 7, 1),
        )

    with pytest.raises(ValueError, match="provider"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)

    assert repository.list_events() == []
    assert repository.get_cursor("upbit", "orders") is None


def test_ingest_provider_events_applies_stale_cursor_updated_at_policy(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.set_cursor("upbit", "orders", "latest", datetime(2026, 6, 7, 2))

    def fetch_page(cursor):
        assert cursor == "latest"
        return ProviderPage([_event("1")], None, "delayed", datetime(2026, 6, 7, 1))

    assert ingest_provider_events(repository, "upbit", "orders", fetch_page) == 0
    assert repository.get_cursor("upbit", "orders") == "latest"
    assert repository.list_events() == []


@pytest.mark.parametrize(
    ("current_checkpoint", "backward_checkpoint"),
    [
        ("10", "9"),
        ("2026-06-07T02:00:00+00:00", "2026-06-07T01:00:00+00:00"),
    ],
)
def test_ingest_provider_events_ignores_same_updated_at_backward_checkpoint_page(
    tmp_path, current_checkpoint, backward_checkpoint
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    updated_at = datetime(2026, 6, 7, 3)
    original = _event("1")
    repository.upsert_event(original)
    repository.set_cursor("upbit", "orders", current_checkpoint, updated_at)

    def fetch_page(cursor):
        assert cursor == current_checkpoint
        return ProviderPage(
            [replace(original, cash_flow_krw=-200_000)],
            None,
            backward_checkpoint,
            updated_at,
        )

    assert ingest_provider_events(repository, "upbit", "orders", fetch_page) == 0
    assert repository.get_cursor("upbit", "orders") == current_checkpoint
    assert repository.list_events()[0].cash_flow_krw == -100_000


def test_ingest_provider_events_accepts_same_updated_at_opaque_checkpoint_page(
    tmp_path,
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    updated_at = datetime(2026, 6, 7, 3)
    original = _event("1")
    repository.upsert_event(original)
    repository.set_cursor("upbit", "orders", "opaque-z", updated_at)

    def fetch_page(cursor):
        assert cursor == "opaque-z"
        return ProviderPage(
            [replace(original, cash_flow_krw=-200_000)],
            None,
            "opaque-a",
            updated_at,
        )

    assert ingest_provider_events(repository, "upbit", "orders", fetch_page) == 0
    assert repository.get_cursor("upbit", "orders") == "opaque-a"
    assert repository.list_events()[0].cash_flow_krw == -200_000


@pytest.mark.parametrize("checkpoint_cursor", ["", "   ", None])
def test_ingest_provider_events_rejects_empty_checkpoint_cursor(
    tmp_path, checkpoint_cursor
) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    def fetch_page(cursor):
        return ProviderPage([], None, checkpoint_cursor, datetime(2026, 6, 7, 1))

    with pytest.raises(ValueError, match="checkpoint_cursor"):
        ingest_provider_events(repository, "upbit", "orders", fetch_page)
