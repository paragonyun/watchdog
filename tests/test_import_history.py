import json
import sqlite3
from datetime import datetime, timezone

import pytest

from portfolio_watchdog.ledger.import_history import import_history_json
from portfolio_watchdog.ledger.models import AssetSnapshot
from portfolio_watchdog.ledger.repository import LedgerRepository


UTC = timezone.utc


def _write_history(path, snapshots, news_items=None) -> bytes:
    original = json.dumps(
        {
            "portfolio_snapshots": snapshots,
            "news_items": news_items or [{"title": "ignored"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    path.write_bytes(original)
    return original


def test_import_history_json_is_repeatable_preserves_local_fields_and_source(tmp_path) -> None:
    history_path = tmp_path / "history.json"
    original = _write_history(
        history_path,
        [
            {
                "captured_at": "2026-06-05T17:00:00+09:00",
                "total_value_krw": 1000,
                "assets": [
                    {
                        "symbol": "BTC",
                        "asset_type": "coin",
                        "value_krw": 1000,
                        "quantity": 0.001,
                        "average_buy_price_krw": 900_000,
                    }
                ],
            }
        ],
    )
    repository = LedgerRepository(tmp_path / "watchdog.db")

    assert import_history_json(history_path, repository) == 1
    assert import_history_json(history_path, repository) == 0

    assert repository.list_account_snapshots()[0].provider == "legacy_history"
    assert repository.list_account_snapshots()[0].captured_at == datetime(
        2026, 6, 5, 8, 0, tzinfo=UTC
    )
    assert repository.list_account_snapshots()[0].data_status == "actual"
    assert repository.list_asset_snapshots() == [
        AssetSnapshot(
            provider="legacy_history",
            captured_at=datetime(2026, 6, 5, 8, 0, tzinfo=UTC),
            asset_symbol="BTC",
            asset_type="coin",
            value_krw=1000,
            quantity=0.001,
            unit_price_krw=None,
            average_buy_price_krw=900_000,
            data_status="actual",
        )
    ]
    assert history_path.read_bytes() == original


def test_import_history_json_ignores_news_items(tmp_path) -> None:
    history_path = tmp_path / "history.json"
    _write_history(history_path, [], news_items=[{"not": "a valid portfolio snapshot"}])

    assert import_history_json(
        history_path, LedgerRepository(tmp_path / "watchdog.db")
    ) == 0


def test_import_history_json_treats_writer_naive_captured_at_as_seoul_time(tmp_path) -> None:
    history_path = tmp_path / "history.json"
    _write_history(
        history_path,
        [{"captured_at": "2026-06-05T08:00:00", "total_value_krw": 1000, "assets": []}],
    )
    repository = LedgerRepository(tmp_path / "watchdog.db")

    import_history_json(history_path, repository)

    assert repository.list_account_snapshots()[0].captured_at == datetime(
        2026, 6, 4, 23, 0, tzinfo=UTC
    )


def test_import_history_json_missing_file_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        import_history_json(
            tmp_path / "missing.json", LedgerRepository(tmp_path / "watchdog.db")
        )


@pytest.mark.parametrize(
    "content",
    [
        "{",
        "[]",
        '{"portfolio_snapshots": {}}',
        '{"portfolio_snapshots": [{"captured_at": "bad", "total_value_krw": 1, "assets": []}]}',
        '{"portfolio_snapshots": [{"captured_at": "2026-06-05T08:00:00", "total_value_krw": 1, "assets": {}}]}',
    ],
)
def test_import_history_json_rejects_invalid_json_or_structure(tmp_path, content) -> None:
    history_path = tmp_path / "history.json"
    history_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        import_history_json(history_path, LedgerRepository(tmp_path / "watchdog.db"))


def test_import_history_json_does_not_partially_store_snapshot_with_invalid_asset(
    tmp_path,
) -> None:
    history_path = tmp_path / "history.json"
    _write_history(
        history_path,
        [
            {
                "captured_at": "2026-06-05T08:00:00",
                "total_value_krw": 1000,
                "assets": [
                    {"symbol": "BTC", "asset_type": "coin", "value_krw": 1000},
                    {"symbol": "", "asset_type": "coin", "value_krw": 0},
                ],
            }
        ],
    )
    repository = LedgerRepository(tmp_path / "watchdog.db")

    with pytest.raises(ValueError):
        import_history_json(history_path, repository)

    assert repository.list_account_snapshots() == []
    assert repository.list_asset_snapshots() == []


@pytest.mark.parametrize(
    ("field", "value", "error_path"),
    [
        ("total_value_krw", float("nan"), r"portfolio_snapshots\[0\]\.total_value_krw"),
        ("value_krw", float("inf"), r"portfolio_snapshots\[0\]\.assets\[0\]\.value_krw"),
        ("quantity", float("-inf"), r"portfolio_snapshots\[0\]\.assets\[0\]\.quantity"),
        ("unit_price_krw", float("nan"), r"portfolio_snapshots\[0\]\.assets\[0\]\.unit_price_krw"),
        (
            "average_buy_price_krw",
            float("inf"),
            r"portfolio_snapshots\[0\]\.assets\[0\]\.average_buy_price_krw",
        ),
    ],
)
def test_import_history_json_rejects_non_finite_numbers(
    tmp_path, field, value, error_path
) -> None:
    history_path = tmp_path / "history.json"
    snapshot = {
        "captured_at": "2026-06-05T08:00:00",
        "total_value_krw": 1000,
        "assets": [
            {
                "symbol": "BTC",
                "asset_type": "coin",
                "value_krw": 1000,
                "quantity": 0.001,
                "unit_price_krw": 1_000_000,
                "average_buy_price_krw": 900_000,
            }
        ],
    }
    target = snapshot if field == "total_value_krw" else snapshot["assets"][0]
    target[field] = value
    _write_history(history_path, [snapshot])
    repository = LedgerRepository(tmp_path / "watchdog.db")

    with pytest.raises(ValueError, match=error_path):
        import_history_json(history_path, repository)

    assert repository.list_account_snapshots() == []
    assert repository.list_asset_snapshots() == []


def test_import_history_json_rolls_back_account_and_assets_on_asset_sql_failure(
    tmp_path,
) -> None:
    history_path = tmp_path / "history.json"
    _write_history(
        history_path,
        [
            {
                "captured_at": "2026-06-05T08:00:00",
                "total_value_krw": 1000,
                "assets": [
                    {"symbol": "BTC", "asset_type": "coin", "value_krw": 1000}
                ],
            }
        ],
    )
    repository = LedgerRepository(tmp_path / "watchdog.db")
    with repository._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_legacy_asset_insert
            BEFORE INSERT ON asset_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'forced asset insert failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced asset insert failure"):
        import_history_json(history_path, repository)

    assert repository.list_account_snapshots() == []
    assert repository.list_asset_snapshots() == []
