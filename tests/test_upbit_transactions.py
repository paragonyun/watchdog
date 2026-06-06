import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlencode

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
    events = parse_upbit_closed_orders(_fixture("upbit_order_details.json"))

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


def test_parse_upbit_closed_orders_ignores_order_without_trades() -> None:
    empty_order = {key: value for key, value in _fixture("upbit_order_details.json")[-1].items() if key != "trades"}
    assert parse_upbit_closed_orders([empty_order]) == []


def test_parse_upbit_closed_orders_dedupes_detail_event_ids() -> None:
    detail = _fixture("upbit_order_details.json")[0]
    assert len(parse_upbit_closed_orders([detail, detail])) == 2


@pytest.mark.parametrize(
    "row",
    [
        {"uuid": "", "market": "KRW-BTC", "side": "bid", "paid_fee": "0", "trades_count": 1, "trades": []},
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades_count": 1,
            "trades": [{"uuid": "", "price": "1", "volume": "1", "funds": "1", "created_at": "2026-01-01T00:00:00Z"}],
        },
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades_count": 1,
            "trades": [{"uuid": "trade", "price": "bad", "volume": "1", "funds": "1", "created_at": "2026-01-01T00:00:00Z"}],
        },
        {
            "uuid": "order",
            "market": "KRW-BTC",
            "side": "bid",
            "paid_fee": "0",
            "trades_count": 1,
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
    assert [(event.cash_flow_krw, event.quantity, event.fee_krw, event.external_cash_flow) for event in withdraws] == [
        (-11000.0, None, 1000.0, True),
        (0.0, -0.0021, 0.0, False),
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

    assert client.list_closed_orders("2026-05-01T00:00:00+00:00", "2026-05-02T00:00:00+00:00", limit=1000) == []

    query = {
        "start_time": "2026-05-01T00:00:00+00:00",
        "end_time": "2026-05-02T00:00:00+00:00",
        "limit": "1000",
        "order_by": "asc",
    }
    assert list(calls[0][1]["params"].items()) == list(query.items())
    assert "page" not in calls[0][1]["params"]
    assert encoded_payloads[0]["query_hash"] == hashlib.sha512(unquote(urlencode(query, doseq=True)).encode()).hexdigest()


def test_upbit_jwt_hash_supports_list_values_without_url_encoding(monkeypatch) -> None:
    payloads = []
    calls = []
    monkeypatch.setattr(upbit.jwt, "encode", lambda payload, *args, **kwargs: payloads.append(payload) or "token")
    monkeypatch.setattr(
        upbit.requests,
        "get",
        lambda url, **kwargs: calls.append((url, kwargs)) or Response([]),
    )
    query = {"states[]": ["done", "cancel"], "market": "KRW-BTC"}
    client = UpbitAccountClient("access", "secret")

    client._request_list("https://api.upbit.com/v1/orders/closed", query)

    query_string = "states[]=done&states[]=cancel&market=KRW-BTC"
    assert payloads[0]["query_hash"] == hashlib.sha512(query_string.encode()).hexdigest()
    assert calls[0][1]["params"] is query


@pytest.mark.parametrize("method", ["list_closed_orders", "list_deposits", "list_withdraws"])
def test_upbit_account_client_validates_list_response(monkeypatch, method) -> None:
    monkeypatch.setattr(upbit.jwt, "encode", lambda *args, **kwargs: "token")
    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: Response({"error": "not a list"}))
    client = UpbitAccountClient("access", "secret")

    args = ("start", "end") if method == "list_closed_orders" else ()
    with pytest.raises(ValueError, match="list"):
        getattr(client, method)(*args)


def test_upbit_account_client_get_order_uses_uuid_and_validates_object(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(upbit.jwt, "encode", lambda *args, **kwargs: "token")
    monkeypatch.setattr(upbit.requests, "get", lambda url, **kwargs: calls.append((url, kwargs)) or Response({"uuid": "order-1"}))
    client = UpbitAccountClient("access", "secret")

    assert client.get_order("order-1") == {"uuid": "order-1"}
    assert calls[0][0] == "https://api.upbit.com/v1/order"
    assert calls[0][1]["params"] == {"uuid": "order-1"}

    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: Response([]))
    with pytest.raises(ValueError, match="object"):
        client.get_order("order-1")


@pytest.mark.parametrize("limit", [0, 1001])
def test_upbit_closed_orders_rejects_limit_outside_official_range(monkeypatch, limit) -> None:
    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: pytest.fail("network called"))
    with pytest.raises(ValueError, match="limit"):
        UpbitAccountClient("access", "secret").list_closed_orders("start", "end", limit=limit)
    with pytest.raises(ValueError, match="limit"):
        fetch_upbit_closed_orders(object(), datetime(2026, 1, 1), datetime(2026, 1, 2), limit=limit)


def test_upbit_account_client_propagates_requests_errors(monkeypatch) -> None:
    error = requests.Timeout("private response detail")
    monkeypatch.setattr(upbit.jwt, "encode", lambda *args, **kwargs: "token")
    monkeypatch.setattr(upbit.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(requests.Timeout) as raised:
        UpbitAccountClient("access", "secret").list_deposits()

    assert raised.value is error


def test_fetch_upbit_closed_orders_splits_saturated_windows_dedupes_and_expands_details() -> None:
    calls = []
    detail_calls = []
    details = {row["uuid"]: row for row in _fixture("upbit_order_details.json")}

    class Client:
        def list_closed_orders(self, start_time, end_time, limit=100):
            calls.append((start_time, end_time, limit))
            if start_time == "2026-01-01T00:00:00+00:00" and end_time == "2026-01-08T00:00:00+00:00":
                return [{"uuid": "saturated-1"}, {"uuid": "saturated-2"}, {"uuid": "saturated-3"}]
            if start_time == "2026-01-01T00:00:00+00:00":
                return [{"uuid": "order-1"}, {"uuid": "order-2"}]
            if end_time == "2026-01-08T00:00:00+00:00":
                return [{"uuid": "order-2"}]
            return [{"uuid": "order-empty"}]

        def get_order(self, order_uuid):
            detail_calls.append(order_uuid)
            return details[order_uuid]

    rows = fetch_upbit_closed_orders(
        Client(),
        datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))),
        datetime(2026, 1, 9, tzinfo=UTC),
        limit=3,
    )

    assert [row["uuid"] for row in rows] == ["order-1", "order-2", "order-empty"]
    assert detail_calls == ["order-1", "order-2", "order-empty"]
    assert calls == [
        ("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00", 3),
        ("2026-01-01T00:00:00+00:00", "2026-01-04T12:00:00+00:00", 3),
        ("2026-01-04T12:00:00+00:00", "2026-01-08T00:00:00+00:00", 3),
        ("2026-01-08T00:00:00+00:00", "2026-01-09T00:00:00+00:00", 3),
    ]


def test_fetch_upbit_closed_orders_expands_official_list_fixture_without_trades() -> None:
    summaries = _fixture("upbit_closed_orders.json")
    details = {row["uuid"]: row for row in _fixture("upbit_order_details.json")}

    class Client:
        def list_closed_orders(self, start_time, end_time, limit=100):
            return summaries

        def get_order(self, order_uuid):
            return details[order_uuid]

    assert all("trades" not in row for row in summaries)
    fetched = fetch_upbit_closed_orders(
        Client(),
        datetime(2026, 5, 1, tzinfo=UTC),
        datetime(2026, 5, 2, tzinfo=UTC),
    )
    assert [row["uuid"] for row in fetched] == ["order-1", "order-2", "order-empty"]


def test_fetch_upbit_closed_orders_treats_naive_datetimes_as_utc() -> None:
    calls = []

    class Client:
        def list_closed_orders(self, start_time, end_time, limit=100):
            calls.append((start_time, end_time, limit))
            return []

        def get_order(self, order_uuid):
            pytest.fail("no detail expected")

    assert fetch_upbit_closed_orders(Client(), datetime(2026, 1, 1), datetime(2026, 1, 2)) == []
    assert calls == [("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", 100)]


def test_fetch_upbit_closed_orders_raises_when_minimum_window_is_saturated(monkeypatch) -> None:
    monkeypatch.setattr(upbit, "MIN_CLOSED_ORDER_WINDOW", timedelta(seconds=1))

    class Client:
        def list_closed_orders(self, start_time, end_time, limit=100):
            return [{"uuid": "order-1"}]

    with pytest.raises(RuntimeError, match="minimum window"):
        fetch_upbit_closed_orders(
            Client(),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            limit=1,
        )


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
