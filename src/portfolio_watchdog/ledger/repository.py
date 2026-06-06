import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Union

from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot, LedgerEvent
from portfolio_watchdog.ledger.schema import SCHEMA_SQL, SCHEMA_VERSION


class LedgerRepository:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT INTO schema_version(version) "
                "SELECT ? WHERE NOT EXISTS (SELECT 1 FROM schema_version)",
                (SCHEMA_VERSION,),
            )

    def upsert_event(self, event: LedgerEvent) -> bool:
        with self._connect() as connection:
            is_new = (
                connection.execute(
                    "SELECT 1 FROM ledger_events WHERE provider = ? AND provider_event_id = ?",
                    (event.provider, event.provider_event_id),
                ).fetchone()
                is None
            )
            connection.execute(
                """
                INSERT INTO ledger_events (
                    provider, provider_event_id, occurred_at, event_type, asset_symbol,
                    cash_flow_krw, quantity, unit_price_krw, fee_krw,
                    external_cash_flow, memo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_event_id) DO UPDATE SET
                    occurred_at = excluded.occurred_at,
                    event_type = excluded.event_type,
                    asset_symbol = excluded.asset_symbol,
                    cash_flow_krw = excluded.cash_flow_krw,
                    quantity = excluded.quantity,
                    unit_price_krw = excluded.unit_price_krw,
                    fee_krw = excluded.fee_krw,
                    external_cash_flow = excluded.external_cash_flow,
                    memo = excluded.memo
                """,
                (
                    event.provider,
                    event.provider_event_id,
                    event.occurred_at.isoformat(),
                    event.event_type,
                    event.asset_symbol,
                    event.cash_flow_krw,
                    event.quantity,
                    event.unit_price_krw,
                    event.fee_krw,
                    int(event.external_cash_flow),
                    event.memo,
                ),
            )
        return is_new

    def list_events(
        self, since: Optional[datetime] = None, until: Optional[datetime] = None
    ) -> list[LedgerEvent]:
        clauses = []
        parameters = []
        if since is not None:
            clauses.append("occurred_at >= ?")
            parameters.append(since.isoformat())
        if until is not None:
            clauses.append("occurred_at <= ?")
            parameters.append(until.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT provider, provider_event_id, occurred_at, event_type, asset_symbol, "
                "cash_flow_krw, quantity, unit_price_krw, fee_krw, external_cash_flow, memo "
                f"FROM ledger_events{where} ORDER BY occurred_at ASC, id ASC",
                parameters,
            ).fetchall()
        return [
            LedgerEvent(
                provider=row["provider"],
                provider_event_id=row["provider_event_id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                event_type=row["event_type"],
                asset_symbol=row["asset_symbol"],
                cash_flow_krw=row["cash_flow_krw"],
                quantity=row["quantity"],
                unit_price_krw=row["unit_price_krw"],
                fee_krw=row["fee_krw"],
                external_cash_flow=bool(row["external_cash_flow"]),
                memo=row["memo"],
            )
            for row in rows
        ]

    def upsert_account_snapshot(self, snapshot: AccountSnapshot) -> bool:
        with self._connect() as connection:
            is_new = (
                connection.execute(
                    "SELECT 1 FROM account_snapshots WHERE provider = ? AND captured_at = ?",
                    (snapshot.provider, snapshot.captured_at.isoformat()),
                ).fetchone()
                is None
            )
            connection.execute(
                """
                INSERT INTO account_snapshots(provider, captured_at, total_value_krw, data_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, captured_at) DO UPDATE SET
                    total_value_krw = excluded.total_value_krw,
                    data_status = excluded.data_status
                """,
                (
                    snapshot.provider,
                    snapshot.captured_at.isoformat(),
                    snapshot.total_value_krw,
                    snapshot.data_status,
                ),
            )
        return is_new

    def list_account_snapshots(
        self, since: Optional[datetime] = None
    ) -> list[AccountSnapshot]:
        where = " WHERE captured_at >= ?" if since is not None else ""
        parameters = (since.isoformat(),) if since is not None else ()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT provider, captured_at, total_value_krw, data_status "
                f"FROM account_snapshots{where} ORDER BY captured_at ASC, id ASC",
                parameters,
            ).fetchall()
        return [
            AccountSnapshot(
                provider=row["provider"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
                total_value_krw=row["total_value_krw"],
                data_status=row["data_status"],
            )
            for row in rows
        ]

    def upsert_asset_snapshot(self, snapshot: AssetSnapshot) -> bool:
        with self._connect() as connection:
            is_new = (
                connection.execute(
                    "SELECT 1 FROM asset_snapshots "
                    "WHERE provider = ? AND captured_at = ? AND asset_symbol = ?",
                    (
                        snapshot.provider,
                        snapshot.captured_at.isoformat(),
                        snapshot.asset_symbol,
                    ),
                ).fetchone()
                is None
            )
            connection.execute(
                """
                INSERT INTO asset_snapshots(
                    provider, captured_at, asset_symbol, asset_type, value_krw,
                    quantity, unit_price_krw, average_buy_price_krw, data_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, captured_at, asset_symbol) DO UPDATE SET
                    asset_type = excluded.asset_type,
                    value_krw = excluded.value_krw,
                    quantity = excluded.quantity,
                    unit_price_krw = excluded.unit_price_krw,
                    average_buy_price_krw = excluded.average_buy_price_krw,
                    data_status = excluded.data_status
                """,
                (
                    snapshot.provider,
                    snapshot.captured_at.isoformat(),
                    snapshot.asset_symbol,
                    snapshot.asset_type,
                    snapshot.value_krw,
                    snapshot.quantity,
                    snapshot.unit_price_krw,
                    snapshot.average_buy_price_krw,
                    snapshot.data_status,
                ),
            )
        return is_new

    def list_asset_snapshots(
        self, captured_at: Optional[datetime] = None
    ) -> list[AssetSnapshot]:
        where = " WHERE captured_at = ?" if captured_at is not None else ""
        parameters = (captured_at.isoformat(),) if captured_at is not None else ()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT provider, captured_at, asset_symbol, asset_type, value_krw, "
                "quantity, unit_price_krw, average_buy_price_krw, data_status "
                f"FROM asset_snapshots{where} ORDER BY captured_at ASC, id ASC",
                parameters,
            ).fetchall()
        return [
            AssetSnapshot(
                provider=row["provider"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
                asset_symbol=row["asset_symbol"],
                asset_type=row["asset_type"],
                value_krw=row["value_krw"],
                quantity=row["quantity"],
                unit_price_krw=row["unit_price_krw"],
                average_buy_price_krw=row["average_buy_price_krw"],
                data_status=row["data_status"],
            )
            for row in rows
        ]

    def get_cursor(self, provider: str, stream: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cursor_value FROM collection_cursors WHERE provider = ? AND stream = ?",
                (provider, stream),
            ).fetchone()
        return None if row is None else row["cursor_value"]

    def set_cursor(
        self, provider: str, stream: str, cursor_value: str, updated_at: datetime
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO collection_cursors(provider, stream, cursor_value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, stream) DO UPDATE SET
                    cursor_value = excluded.cursor_value,
                    updated_at = excluded.updated_at
                """,
                (provider, stream, cursor_value, updated_at.isoformat()),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
