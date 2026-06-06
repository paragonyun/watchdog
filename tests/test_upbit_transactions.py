import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest
import requests

from portfolio_watchdog.providers import upbit
from portfolio_watchdog.providers.upbit import (
    UpbitAccountClient,
    fetch_upbit_closed_orders,
    fetch_upbit_deposits,
    fetch_upbit_withdraws,
    parse_upbit_closed_orders,
    parse_upbit_deposits,
    parse_upbit_withdraws,
)


FIXTURES = Path(__file__).parent / "fixtures"
UTC = timezone.utc


def _fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_upbit_closed_orders_emits_one_event_per_trade_with_fee_and_direction() -> None:
    events = parse_upbit_closed_orders(_fixture("upbit_closed_orders.json"))

    assert [event.provider_event_id for event in events] == [
        "order-1:trade-1",
        "order-1:trade-2",
        "order-2:trade-3",
    ]
    assert [event.event_type for event in events] == ["buy", "buy", "sell"]
    assert all(event.provider == "upbit" and event.asset_symbol == "BTC" for event in events)
    assert [event.quantity for event in events] == [0.001, 0.002, -0.003]
    assert [event.fee_krw for event in events] == [5.0, 10.0, 2.5]
    assert [event.cash_flow_krw for event in events] == [-10005.0, -20010.0, 29997.5]
    assert events[0].occurred_at == datetime(2026, 5, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    assert all(event.external_cash_flow is False for event in events)


@pytest.mark.parametrize(
    "row",
    [
        {"uuid": "", "market": "KRW-BTC", "side": "bid", "paid_fee": "0", "trades": []},
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades": [{"uuid": "", "price": "1", "volume": "1", "funds": "1", "created_at": "2026-01-01T00:00:00Z"}],
        },
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades": [{"uuid": "trade", "price": "bad", "volume": "1", "funds": "1", "created_at": "2026-01-01T00:00:00Z"}],
        },
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades": [{"uuid": "trade", "price": "1", "volume": "1", "funds": "1", "created_at": ""}],
        },
    ],
)
def test_parse_upbit_closed_orders_validates_required_ids_times_and_numbers(row) -> None:
    with pytest.raises(ValueError):
        parse_upbit_closed_orders([row])


def test_parse_upbit_deposits_and_withdraws_only_emit_completed_flows() -> None:
    deposits = parse_upbit_deposits(_fixture("upbit_deposits.json"))
    withdraws = parse_upbit_withdraws(_fixture("upbit_withdraws.json"))

    assert [(event.provider_event_id, event.event_type) for event in deposits] == [
        ("deposit-krw", "deposit"),
        ("deposit-btc", "deposit"),
    ]
    assert [(event.cash_flow_krw, event.quantity, event.external_cash_flow) for event in deposits] == [
        (50000.0, None, True),
        (0.0, 0.01, False),
    ]
    assert [(event.provider_event_id, event.event_type) for event in withdraws] == [
        ("withdraw-krw", "withdrawal"),
        ("withdraw-btc", "withdrawal"),
    ]
    assert [(event.cash_flow_krw, event.quantity, event.external_cash_flow) for event in withdraws] == [
        (-10000.0, None, True),
        (0.0, -0.002, False),
    ]


@pytest.mark.parametrize("parser,state", [(parse_upbit_deposits, "ACCEPTED"), (parse_upbit_withdraws, "DONE")])
def test_parse_upbit_transfers_validate_required_ids_times_and_numbers(parser, state) -> None:
    base = {"uuid": "transfer", "currency": "BTC", "amount": "1", "state": state, "done_at": "2026-01-01T00:00:00Z"}
    for field, value in [("uuid", ""), ("currency", ""), ("amount", "bad"), ("done_at", "")]:
        with pytest.raises(ValueError):
            parser([{**base, field: value}])


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_upbit_account_client_uses_identical_ordered_query_for_jwt_and_request(monkeypatch) -> None:
    encoded_payloads = []
    calls = []
    monkeypatch.setattr(upbit.jwt, "encode", lambda payload, *args, **kwargs: encoded_payloads.append(payload) or "token")
    monkeypatch.setattr(
        upbit.requests,
        "get",
        lambda url, **kwargs: calls.append((url, kwargs)) or Response([]),
    )
    client = UpbitAccountClient("access", "secret")

    assert client.list_closed_orders("2026-05-01T00:00:00+00:00", "2026-05-02T00:00:00+00:00", page=2, limit=50) == []

    query = {
        "start_time": "2026-05-01T00:00:00+00:00",
        "end_time": "2026-05-02T00:00:00+00:00",
        "page": "2",
        "limit": "50",
        "order_by": "asc",
    }
    assert list(calls[0][1]["params"].items()) == list(query.items())
    assert encoded_payloads[0]["query_hash"] == hashlib.sha512(urlencode(query).encode()).hexdigest()


@pytest.mark.parametrize("method", ["list_closed_orders", "list_deposits", "list_withdraws"])
def test_upbit_account_client_validates_list_response(monkeypatch, method) -> None:
    monkeypatch.setattr(upbit.jwt, "encode", lambda *args, **kwargs: "token")
    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: Response({"error": "not a list"}))
    client = UpbitAccountClient("access", "secret")

    args = ("start", "end") if method == "list_closed_orders" else ()
    with pytest.raises(ValueError, match="list"):
        getattr(client, method)(*args)


def test_upbit_account_client_propagates_requests_errors(monkeypatch) -> None:
    error = requests.Timeout("private response detail")
    monkeypatch.setattr(upbit.jwt, "encode", lambda *args, **kwargs: "token")
    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(requests.Timeout) as raised:
        UpbitAccountClient("access", "secret").list_deposits()

    assert raised.value is error


def test_fetch_upbit_closed_orders_splits_seven_days_paginates_and_uses_utc_iso() -> None:
    calls = []

    class Client:
        def list_closed_orders(self, start_time, end_time, page=1, limit=100):
            calls.append((start_time, end_time, page, limit))
            return [{"page": page}] * (limit if len(calls) == 1 else 1)

    rows = fetch_upbit_closed_orders(
        Client(),
        datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))),
        datetime(2026, 1, 16, tzinfo=UTC),
        limit=2,
    )

    assert len(rows) == 5
    assert calls == [
        ("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00", 1, 2),
        ("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00", 2, 2),
        ("2026-01-08T00:00:00+00:00", "2026-01-15T00:00:00+00:00", 1, 2),
        ("2026-01-15T00:00:00+00:00", "2026-01-16T00:00:00+00:00", 1, 2),
    ]


def test_fetch_upbit_transfer_helpers_paginate_until_short_page() -> None:
    calls = []

    class Client:
        def list_deposits(self, page=1, limit=100):
            calls.append(("deposit", page, limit))
            return [{}] * (limit if page == 1 else 1)

        def list_withdraws(self, page=1, limit=100):
            calls.append(("withdraw", page, limit))
            return []

    client = Client()
    assert len(fetch_upbit_deposits(client, limit=2)) == 3
    assert fetch_upbit_withdraws(client, limit=2) == []
    assert calls == [("deposit", 1, 2), ("deposit", 2, 2), ("withdraw", 1, 2)]


def test_fetch_helpers_raise_at_page_limit_to_prevent_infinite_loop(monkeypatch) -> None:
    monkeypatch.setattr(upbit, "MAX_PAGES_PER_REQUEST", 2)

    class Client:
        def list_deposits(self, page=1, limit=100):
            return [{}] * limit

    with pytest.raises(RuntimeError, match="page limit"):
        fetch_upbit_deposits(Client(), limit=1)
