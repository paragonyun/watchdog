import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from portfolio_watchdog.ledger.models import LedgerEvent
from portfolio_watchdog.ledger.repository import LedgerRepository


MAX_PAGES = 1000


@dataclass(frozen=True)
class ProviderPage:
    events: list[LedgerEvent]
    next_page_cursor: str | None
    checkpoint_cursor: str
    checkpoint_updated_at: datetime


def add_manual_cash_flow(
    repository: LedgerRepository,
    occurred_at: datetime,
    amount_krw: float,
    memo: str,
    idempotency_key: str,
) -> bool:
    amount = _non_zero_finite_number(amount_krw, "amount_krw")
    _non_empty_string(idempotency_key, "idempotency_key")
    _non_empty_string(memo, "memo")
    return repository.insert_manual_event(
        LedgerEvent(
            provider="manual",
            provider_event_id=idempotency_key,
            occurred_at=occurred_at,
            event_type="deposit" if amount > 0 else "withdrawal",
            asset_symbol=None,
            cash_flow_krw=amount,
            quantity=None,
            unit_price_krw=None,
            fee_krw=0,
            external_cash_flow=True,
            memo=memo,
        )
    )


def ingest_provider_events(
    repository: LedgerRepository,
    provider: str,
    stream: str,
    fetch_page: Callable[[str | None], ProviderPage],
) -> int:
    _non_empty_string(provider, "provider")
    _non_empty_string(stream, "stream")
    checkpoint_cursor = repository.get_cursor(provider, stream)
    page_cursor = checkpoint_cursor
    seen_page_cursors = {page_cursor} if page_cursor is not None else set()
    inserted_count = 0

    for _ in range(MAX_PAGES):
        page = fetch_page(page_cursor)
        if not isinstance(page, ProviderPage):
            raise TypeError("fetch_page must return ProviderPage")
        if any(event.provider != provider for event in page.events):
            raise ValueError("event.provider must match provider")
        _non_empty_string(page.checkpoint_cursor, "checkpoint_cursor")
        if page.next_page_cursor is not None:
            _non_empty_string(page.next_page_cursor, "next_page_cursor")
            if page.next_page_cursor in seen_page_cursors:
                raise RuntimeError("repeated next_page_cursor")

        inserted_count += repository.upsert_event_page(
            page.events,
            provider,
            stream,
            page.checkpoint_cursor,
            page.checkpoint_updated_at,
        )
        if page.next_page_cursor is None:
            return inserted_count
        page_cursor = page.next_page_cursor
        seen_page_cursors.add(page_cursor)

    raise RuntimeError(f"page limit exceeded: {MAX_PAGES}")


def _non_zero_finite_number(value: float, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-zero finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a non-zero finite number") from error
    if not math.isfinite(number) or number == 0:
        raise ValueError(f"{field} must be a non-zero finite number")
    return number


def _non_empty_string(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
