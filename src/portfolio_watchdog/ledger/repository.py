import math
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterator, Optional, Sequence, Union

from portfolio_watchdog.ledger.models import AccountSnapshot, AssetSnapshot, LedgerEvent
from portfolio_watchdog.ledger.schema import SCHEMA_STATEMENTS, SCHEMA_VERSION
from portfolio_watchdog.performance.benchmark import BenchmarkWeight


BUSY_TIMEOUT_MS = 5000
BUSY_RETRY_ATTEMPTS = 3
BUSY_RETRY_DELAY_SECONDS = 0.05
_INITIALIZATION_LOCK = Lock()


class LedgerRepository:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _INITIALIZATION_LOCK:
            self._initialize_schema()

    def upsert_event(self, event: LedgerEvent) -> bool:
        with self._connect() as connection:
            return _upsert_event(connection, event)

    def insert_manual_event(self, event: LedgerEvent) -> bool:
        values = _event_values(event)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT provider, provider_event_id, occurred_at, event_type, asset_symbol,
                    cash_flow_krw, quantity, unit_price_krw, fee_krw,
                    external_cash_flow, memo
                FROM ledger_events
                WHERE provider = ? AND provider_event_id = ?
                """,
                values[:2],
            ).fetchone()
            if existing is not None:
                if tuple(existing) == values:
                    return False
                raise ValueError("manual cash flow idempotency conflict")
            _insert_event(connection, values)
        return True

    def upsert_event_page(
        self,
        events: Sequence[LedgerEvent],
        provider: str,
        stream: str,
        checkpoint_cursor: str,
        checkpoint_updated_at: datetime,
    ) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not _cursor_would_be_accepted(
                connection,
                provider,
                stream,
                checkpoint_cursor,
                checkpoint_updated_at,
            ):
                return 0
            inserted_count = sum(_upsert_event(connection, event) for event in events)
            _set_cursor(
                connection, provider, stream, checkpoint_cursor, checkpoint_updated_at
            )
        return inserted_count

    def list_events(
        self, since: Optional[datetime] = None, until: Optional[datetime] = None
    ) -> list[LedgerEvent]:
        clauses = []
        parameters = []
        if since is not None:
            clauses.append("occurred_at >= ?")
            parameters.append(_utc_iso(since))
        if until is not None:
            clauses.append("occurred_at <= ?")
            parameters.append(_utc_iso(until))
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
                occurred_at=_from_utc_iso(row["occurred_at"]),
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
        values = (
            snapshot.provider,
            _utc_iso(snapshot.captured_at),
            snapshot.total_value_krw,
            snapshot.data_status,
        )
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO account_snapshots(provider, captured_at, total_value_krw, data_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, captured_at) DO NOTHING
                RETURNING 1
                """,
                values,
            ).fetchone()
            if inserted is None:
                connection.execute(
                    """
                    UPDATE account_snapshots SET total_value_krw = ?, data_status = ?
                    WHERE provider = ? AND captured_at = ?
                    """,
                    (*values[2:], *values[:2]),
                )
        return inserted is not None

    def list_account_snapshots(
        self, since: Optional[datetime] = None
    ) -> list[AccountSnapshot]:
        where = " WHERE captured_at >= ?" if since is not None else ""
        parameters = (_utc_iso(since),) if since is not None else ()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT provider, captured_at, total_value_krw, data_status "
                f"FROM account_snapshots{where} ORDER BY captured_at ASC, id ASC",
                parameters,
            ).fetchall()
        return [
            AccountSnapshot(
                provider=row["provider"],
                captured_at=_from_utc_iso(row["captured_at"]),
                total_value_krw=row["total_value_krw"],
                data_status=row["data_status"],
            )
            for row in rows
        ]

    def upsert_asset_snapshot(self, snapshot: AssetSnapshot) -> bool:
        values = (
            snapshot.provider,
            _utc_iso(snapshot.captured_at),
            snapshot.asset_symbol,
            snapshot.asset_type,
            snapshot.value_krw,
            snapshot.quantity,
            snapshot.unit_price_krw,
            snapshot.average_buy_price_krw,
            snapshot.data_status,
        )
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO asset_snapshots(
                    provider, captured_at, asset_symbol, asset_type, value_krw,
                    quantity, unit_price_krw, average_buy_price_krw, data_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, captured_at, asset_symbol) DO NOTHING
                RETURNING 1
                """,
                values,
            ).fetchone()
            if inserted is None:
                connection.execute(
                    """
                    UPDATE asset_snapshots SET
                        asset_type = ?, value_krw = ?, quantity = ?, unit_price_krw = ?,
                        average_buy_price_krw = ?, data_status = ?
                    WHERE provider = ? AND captured_at = ? AND asset_symbol = ?
                    """,
                    (*values[3:], *values[:3]),
                )
        return inserted is not None

    def upsert_snapshot(
        self, account: AccountSnapshot, assets: Sequence[AssetSnapshot]
    ) -> bool:
        account_values = (
            account.provider,
            _utc_iso(account.captured_at),
            account.total_value_krw,
            account.data_status,
        )
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO account_snapshots(provider, captured_at, total_value_krw, data_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, captured_at) DO NOTHING
                RETURNING 1
                """,
                account_values,
            ).fetchone()
            if inserted is None:
                connection.execute(
                    """
                    UPDATE account_snapshots SET total_value_krw = ?, data_status = ?
                    WHERE provider = ? AND captured_at = ?
                    """,
                    (*account_values[2:], *account_values[:2]),
                )
            for asset in assets:
                asset_values = (
                    asset.provider,
                    _utc_iso(asset.captured_at),
                    asset.asset_symbol,
                    asset.asset_type,
                    asset.value_krw,
                    asset.quantity,
                    asset.unit_price_krw,
                    asset.average_buy_price_krw,
                    asset.data_status,
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
                    asset_values,
                )
        return inserted is not None

    def list_asset_snapshots(
        self, captured_at: Optional[datetime] = None
    ) -> list[AssetSnapshot]:
        where = " WHERE captured_at = ?" if captured_at is not None else ""
        parameters = (_utc_iso(captured_at),) if captured_at is not None else ()
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
                captured_at=_from_utc_iso(row["captured_at"]),
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
            connection.execute("BEGIN IMMEDIATE")
            _set_cursor(connection, provider, stream, cursor_value, updated_at)

    def save_target_allocation(self, weights: Sequence[BenchmarkWeight]) -> bool:
        validated = _validate_target_allocation(weights)
        effective_from = validated[0].effective_from.isoformat()
        requested_items = [
            (weight.asset_group, weight.weight, weight.benchmark_symbol)
            for weight in validated
        ]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM target_allocation_versions WHERE effective_from = ?",
                (effective_from,),
            ).fetchone()
            if existing is not None:
                stored_items = connection.execute(
                    """
                    SELECT asset_group, target_weight, benchmark_symbol
                    FROM target_allocation_items
                    WHERE version_id = ?
                    ORDER BY asset_group
                    """,
                    (existing["id"],),
                ).fetchall()
                if [tuple(row) for row in stored_items] == requested_items:
                    return False
                raise ValueError("target allocation version conflict")

            cursor = connection.execute(
                """
                INSERT INTO target_allocation_versions(effective_from, created_at)
                VALUES (?, ?)
                """,
                (effective_from, _utc_iso(datetime.now(timezone.utc))),
            )
            connection.executemany(
                """
                INSERT INTO target_allocation_items(
                    version_id, asset_group, target_weight, benchmark_symbol
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (cursor.lastrowid, asset_group, target_weight, benchmark_symbol)
                    for asset_group, target_weight, benchmark_symbol in requested_items
                ],
            )
        return True

    def get_target_allocation(self, effective_on: date) -> list[BenchmarkWeight]:
        if type(effective_on) is not date:
            raise ValueError("effective_on must be a date")
        with self._connect() as connection:
            version = connection.execute(
                """
                SELECT id, effective_from
                FROM target_allocation_versions
                WHERE effective_from <= ?
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                (effective_on.isoformat(),),
            ).fetchone()
            if version is None:
                return []
            rows = connection.execute(
                """
                SELECT asset_group, target_weight, benchmark_symbol
                FROM target_allocation_items
                WHERE version_id = ?
                ORDER BY asset_group
                """,
                (version["id"],),
            ).fetchall()
        effective_from = date.fromisoformat(version["effective_from"])
        return [
            BenchmarkWeight(
                effective_from=effective_from,
                asset_group=row["asset_group"],
                weight=row["target_weight"],
                benchmark_symbol=row["benchmark_symbol"],
            )
            for row in rows
        ]

    def _initialize_schema(self) -> None:
        for attempt in range(BUSY_RETRY_ATTEMPTS):
            try:
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(SCHEMA_STATEMENTS[0])
                    versions = connection.execute(
                        "SELECT version FROM schema_version"
                    ).fetchall()
                    if not versions:
                        connection.execute(
                            "INSERT INTO schema_version(version) VALUES (?)",
                            (SCHEMA_VERSION,),
                        )
                    elif len(versions) != 1 or versions[0]["version"] != SCHEMA_VERSION:
                        raise RuntimeError(
                            f"Unsupported ledger schema version rows: "
                            f"{[row['version'] for row in versions]}"
                        )
                    for statement in SCHEMA_STATEMENTS[1:]:
                        connection.execute(statement)
                return
            except sqlite3.OperationalError as error:
                if not _is_busy_error(error) or attempt == BUSY_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(BUSY_RETRY_DELAY_SECONDS)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            connection.execute("PRAGMA foreign_keys = ON")
            _enable_wal(connection)
            with connection:
                yield connection
        finally:
            connection.close()


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _validate_target_allocation(
    weights: Sequence[BenchmarkWeight],
) -> list[BenchmarkWeight]:
    validated = list(weights)
    if not validated:
        raise ValueError("weights must not be empty")

    effective_from = validated[0].effective_from
    asset_groups = set()
    for weight in validated:
        if type(weight.effective_from) is not date:
            raise ValueError("effective_from must be a date")
        if not isinstance(weight.asset_group, str) or not weight.asset_group:
            raise ValueError("asset_group must be a non-empty string")
        if not isinstance(weight.benchmark_symbol, str) or not weight.benchmark_symbol:
            raise ValueError("benchmark_symbol must be a non-empty string")
        try:
            finite = math.isfinite(weight.weight)
        except TypeError:
            finite = False
        if not finite or weight.weight < 0:
            raise ValueError("weight must be finite and nonnegative")
        if weight.effective_from != effective_from:
            raise ValueError("weights must have the same effective_from")
        if weight.asset_group in asset_groups:
            raise ValueError(f"duplicate asset_group: {weight.asset_group}")
        asset_groups.add(weight.asset_group)

    if abs(math.fsum(weight.weight for weight in validated) - 1.0) > 0.0001:
        raise ValueError("weight sum must be within 0.0001 of 1.0")
    return sorted(validated, key=lambda weight: weight.asset_group)


def _upsert_event(connection: sqlite3.Connection, event: LedgerEvent) -> bool:
    values = _event_values(event)
    inserted = _insert_event(connection, values)
    if not inserted:
        # Without a provider revision, the last upsert call is the correction source.
        connection.execute(
            """
            UPDATE ledger_events SET
                occurred_at = ?, event_type = ?, asset_symbol = ?,
                cash_flow_krw = ?, quantity = ?, unit_price_krw = ?,
                fee_krw = ?, external_cash_flow = ?, memo = ?
            WHERE provider = ? AND provider_event_id = ?
            """,
            (*values[2:], values[0], values[1]),
        )
    return inserted


def _event_values(event: LedgerEvent) -> tuple:
    return (
        event.provider,
        event.provider_event_id,
        _utc_iso(event.occurred_at),
        event.event_type,
        event.asset_symbol,
        event.cash_flow_krw,
        event.quantity,
        event.unit_price_krw,
        event.fee_krw,
        int(event.external_cash_flow),
        event.memo,
    )


def _insert_event(connection: sqlite3.Connection, values: tuple) -> bool:
    return (
        connection.execute(
            """
            INSERT INTO ledger_events (
                provider, provider_event_id, occurred_at, event_type, asset_symbol,
                cash_flow_krw, quantity, unit_price_krw, fee_krw,
                external_cash_flow, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, provider_event_id) DO NOTHING
            RETURNING 1
            """,
            values,
        ).fetchone()
        is not None
    )


def _cursor_would_be_accepted(
    connection: sqlite3.Connection,
    provider: str,
    stream: str,
    cursor_value: str,
    updated_at: datetime,
) -> bool:
    existing = connection.execute(
        "SELECT cursor_value, updated_at FROM collection_cursors "
        "WHERE provider = ? AND stream = ?",
        (provider, stream),
    ).fetchone()
    if existing is None:
        return True
    existing_updated_at = _from_utc_iso(existing["updated_at"])
    new_updated_at = _from_utc_iso(_utc_iso(updated_at))
    if new_updated_at < existing_updated_at:
        return False
    return new_updated_at != existing_updated_at or not _cursor_moves_backward(
        existing["cursor_value"], cursor_value
    )


def _set_cursor(
    connection: sqlite3.Connection,
    provider: str,
    stream: str,
    cursor_value: str,
    updated_at: datetime,
) -> None:
    if not _cursor_would_be_accepted(
        connection, provider, stream, cursor_value, updated_at
    ):
        return
    connection.execute(
        """
        INSERT INTO collection_cursors(provider, stream, cursor_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(provider, stream) DO UPDATE SET
            cursor_value = excluded.cursor_value,
            updated_at = excluded.updated_at
        """,
        (provider, stream, cursor_value, _utc_iso(updated_at)),
    )


def _from_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _enable_wal(connection: sqlite3.Connection) -> None:
    for attempt in range(BUSY_RETRY_ATTEMPTS):
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as error:
            if not _is_busy_error(error) or attempt == BUSY_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(BUSY_RETRY_DELAY_SECONDS)


def _is_busy_error(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _cursor_moves_backward(existing: str, new: str) -> bool:
    existing_number = _parse_int(existing)
    new_number = _parse_int(new)
    if existing_number is not None and new_number is not None:
        return new_number < existing_number

    existing_datetime = _parse_iso_datetime(existing)
    new_datetime = _parse_iso_datetime(new)
    if existing_datetime is not None and new_datetime is not None:
        return new_datetime < existing_datetime

    # Opaque cursors have provider-defined ordering, so callers own monotonicity.
    return False


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    try:
        return _from_utc_iso(value)
    except ValueError:
        return None
