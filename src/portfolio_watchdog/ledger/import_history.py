import json
from datetime import datetime
from pathlib import Path
from typing import Any

from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot
from portfolio_watchdog.ledger.repository import LedgerRepository


PROVIDER = "legacy_history"
DATA_STATUS = "actual"


def import_history_json(history_path: Path, repository: LedgerRepository) -> int:
    path = Path(history_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid history JSON: {path}") from error

    if not isinstance(data, dict):
        raise ValueError("History JSON root must be an object")
    snapshots = data.get("portfolio_snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("portfolio_snapshots must be a list")

    inserted_count = 0
    for index, item in enumerate(snapshots):
        account, assets = _snapshot(item, index)
        inserted_count += repository.upsert_snapshot(account, assets)
    return inserted_count


def _snapshot(item: Any, index: int) -> tuple[AccountSnapshot, list[AssetSnapshot]]:
    if not isinstance(item, dict):
        raise ValueError(f"portfolio_snapshots[{index}] must be an object")

    captured_at = _datetime(
        item.get("captured_at"), f"portfolio_snapshots[{index}].captured_at"
    )
    account = AccountSnapshot(
        provider=PROVIDER,
        captured_at=captured_at,
        total_value_krw=_number(
            item.get("total_value_krw"), f"portfolio_snapshots[{index}].total_value_krw"
        ),
        data_status=DATA_STATUS,
    )
    raw_assets = item.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ValueError(f"portfolio_snapshots[{index}].assets must be a list")
    assets = [
        _asset(raw_asset, index, asset_index, captured_at)
        for asset_index, raw_asset in enumerate(raw_assets)
    ]
    return account, assets


def _asset(
    item: Any, snapshot_index: int, asset_index: int, captured_at: datetime
) -> AssetSnapshot:
    field = f"portfolio_snapshots[{snapshot_index}].assets[{asset_index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{field} must be an object")
    symbol = item.get("symbol")
    asset_type = item.get("asset_type")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError(f"{field}.symbol must be a non-empty string")
    if not isinstance(asset_type, str) or not asset_type:
        raise ValueError(f"{field}.asset_type must be a non-empty string")
    return AssetSnapshot(
        provider=PROVIDER,
        captured_at=captured_at,
        asset_symbol=symbol,
        asset_type=asset_type,
        value_krw=_number(item.get("value_krw"), f"{field}.value_krw"),
        quantity=_optional_number(item.get("quantity"), f"{field}.quantity"),
        unit_price_krw=_optional_number(
            item.get("unit_price_krw"), f"{field}.unit_price_krw"
        ),
        average_buy_price_krw=_optional_number(
            item.get("average_buy_price_krw"), f"{field}.average_buy_price_krw"
        ),
        data_status=DATA_STATUS,
    )


def _datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO datetime string") from error


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error


def _optional_number(value: Any, field: str) -> float | None:
    return None if value is None else _number(value, field)
