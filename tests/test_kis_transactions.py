import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from portfolio_watchdog.providers import kis
from portfolio_watchdog.providers.kis import KisDomesticStockClient, parse_kis_daily_executions


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture() -> list[dict]:
    return json.loads((FIXTURES / "kis_daily_executions.json").read_text(encoding="utf-8"))


def _recent_dates() -> tuple[str, str]:
    today = datetime.now(kis.KST).date()
    return (today - timedelta(days=30)).strftime("%Y%m%d"), today.strftime("%Y%m%d")


def test_parse_kis_daily_executions_maps_direction_and_uses_order_time_as_approximation() -> None:
    events = parse_kis_daily_executions(_fixture(), {"005930": "SAMSUNG"})

    assert [event.provider_event_id for event in events] == [
        "20260501:00123:0000001001",
        "20260502:00123:0000001002",
        "20260504:00123:0000001004",
    ]
    assert [event.event_type for event in events] == ["buy", "sell", "buy"]
    assert all(event.provider == "kis" and event.asset_symbol == "SAMSUNG" for event in events)
    assert [(event.quantity, event.unit_price_krw) for event in events] == [
        (2.0, 70000.0),
        (-1.0, 71000.0),
        (1.0, 50000.0),
    ]
    assert [(event.fee_krw, event.cash_flow_krw) for event in events] == [
        (0.0, -140000.0),
        (0.0, 71000.0),
        (0.0, -50000.0),
    ]
    assert events[0].occurred_at == datetime(2026, 5, 1, 0, 15, 30, tzinfo=timezone.utc)
    assert events[1].occurred_at == datetime(2026, 5, 2, 1, 15, tzinfo=timezone.utc)
    assert events[2].occurred_at == datetime(2026, 5, 4, 4, 0, tzinfo=timezone.utc)


def test_parse_kis_daily_executions_rejects_missing_order_time() -> None:
    row = {
        **{key: value for key, value in _fixture()[0].items() if key != "ord_tmd"},
        "ccld_tmd": "101500",
    }

    with pytest.raises(ValueError, match="ord_tmd"):
        parse_kis_daily_executions([row], {"005930": "SAMSUNG"})


def test_parse_kis_daily_executions_dedupes_reverse_order_using_first_latest_row() -> None:
    events = parse_kis_daily_executions([_fixture()[0], _fixture()[-1]], {"005930": "SAMSUNG"})

    assert len(events) == 1
    assert events[0].quantity == 2.0
    assert events[0].cash_flow_krw == -140000.0


def test_parse_kis_daily_executions_ignores_unofficial_fee_fields() -> None:
    row = {**_fixture()[0], "fee": "100", "tax": "20"}

    event = parse_kis_daily_executions([row], {"005930": "SAMSUNG"})[0]

    assert event.fee_krw == 0
    assert event.cash_flow_krw == -140000


def test_parse_kis_daily_executions_rejects_unmapped_symbol() -> None:
    with pytest.raises(ValueError, match="005930"):
        parse_kis_daily_executions([_fixture()[0]], {})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tot_ccld_qty", "bad"),
        ("avg_prvs", "-1"),
        ("tot_ccld_amt", "bad"),
    ],
)
def test_parse_kis_daily_executions_validates_execution_totals(field, value) -> None:
    row = {**_fixture()[0], field: value}

    with pytest.raises(ValueError, match=field):
        parse_kis_daily_executions([row], {"005930": "SAMSUNG"})


def test_parse_kis_daily_executions_allows_rounded_total_amount() -> None:
    row = {**_fixture()[0], "tot_ccld_amt": "139999"}

    event = parse_kis_daily_executions([row], {"005930": "SAMSUNG"})[0]

    assert event.cash_flow_krw == -139999


class Response:
    def __init__(self, payload, headers=None, error=None):
        self.payload = payload
        self.headers = headers or {}
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class TokenClient:
    app_key = "app-key"
    app_secret = "app-secret"
    base_url = "https://example.test"

    def __init__(self, env="real"):
        self.env = env

    def get_access_token(self):
        return "secret-token"


def test_kis_daily_executions_uses_official_request_and_continuation(monkeypatch) -> None:
    start_date, end_date = _recent_dates()
    calls = []
    responses = iter(
        [
            Response(
                {"output1": [{"odno": "1"}], "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"},
                {"tr_cont": "M"},
            ),
            Response({"output1": [{"odno": "2"}]}, {"tr_cont": ""}),
        ]
    )
    monkeypatch.setattr(kis.requests, "get", lambda url, **kwargs: calls.append((url, kwargs)) or next(responses))

    rows = KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(start_date, end_date)

    assert rows == [{"odno": "1"}, {"odno": "2"}]
    assert [call[0] for call in calls] == [
        "https://example.test/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
        "https://example.test/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
    ]
    assert calls[0][1]["headers"]["tr_id"] == "TTTC0081R"
    assert calls[0][1]["headers"]["tr_cont"] == ""
    assert calls[1][1]["headers"]["tr_cont"] == "N"
    assert calls[0][1]["params"] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "INQR_STRT_DT": start_date,
        "INQR_END_DT": end_date,
        "SLL_BUY_DVSN_CD": "00",
        "PDNO": "",
        "CCLD_DVSN": "00",
        "INQR_DVSN": "00",
        "INQR_DVSN_3": "00",
        "ORD_GNO_BRNO": "",
        "ODNO": "",
        "INQR_DVSN_1": "",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
        "EXCG_ID_DVSN_CD": "ALL",
    }
    assert calls[1][1]["params"]["CTX_AREA_FK100"] == "FK"
    assert calls[1][1]["params"]["CTX_AREA_NK100"] == "NK"
    assert all(call[1]["timeout"] == 10 for call in calls)


def test_kis_daily_executions_uses_virtual_tr_id(monkeypatch) -> None:
    today = datetime.now(kis.KST).strftime("%Y%m%d")
    calls = []
    monkeypatch.setattr(kis.requests, "get", lambda url, **kwargs: calls.append(kwargs) or Response({"output1": []}))

    KisDomesticStockClient(TokenClient("virtual"), "12345678", "01").get_daily_executions(today, today)

    assert calls[0]["headers"]["tr_id"] == "VTTC0081R"


@pytest.mark.parametrize(
    ("start_offset", "end_offset"),
    [(0, -1), (-91, 0), (0, 1)],
)
def test_kis_daily_executions_rejects_dates_outside_recent_90_days_without_request(
    monkeypatch, start_offset, end_offset
) -> None:
    today = datetime.now(kis.KST).date()
    start_date = (today + timedelta(days=start_offset)).strftime("%Y%m%d")
    end_date = (today + timedelta(days=end_offset)).strftime("%Y%m%d")
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: pytest.fail("network called"))

    with pytest.raises(ValueError, match="date"):
        KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(start_date, end_date)


def test_kis_daily_executions_allows_start_exactly_90_days_ago(monkeypatch) -> None:
    today = datetime.now(kis.KST).date()
    calls = []
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: calls.append(kwargs) or Response({"output1": []}))

    KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(
        (today - timedelta(days=90)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    )

    assert len(calls) == 1


@pytest.mark.parametrize("start_date", ["2026-05-01", "2026051"])
def test_kis_daily_executions_rejects_invalid_date_format_without_request(monkeypatch, start_date) -> None:
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: pytest.fail("network called"))

    with pytest.raises(ValueError, match="date"):
        KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(
            start_date, datetime.now(kis.KST).strftime("%Y%m%d")
        )


def test_kis_daily_executions_validates_output_and_repeated_cursor(monkeypatch) -> None:
    today = datetime.now(kis.KST).strftime("%Y%m%d")
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: Response({"output1": {}}))
    client = KisDomesticStockClient(TokenClient(), "12345678", "01")
    with pytest.raises(ValueError, match="output1"):
        client.get_daily_executions(today, today)

    monkeypatch.setattr(
        kis.requests,
        "get",
        lambda *args, **kwargs: Response(
            {"output1": [], "ctx_area_fk100": "SAME", "ctx_area_nk100": "SAME"},
            {"tr_cont": "M"},
        ),
    )
    with pytest.raises(RuntimeError, match="cursor"):
        client.get_daily_executions(today, today)


def test_kis_daily_executions_propagates_request_errors(monkeypatch) -> None:
    today = datetime.now(kis.KST).strftime("%Y%m%d")
    error = requests.Timeout("private response detail")
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: Response({}, error=error))

    with pytest.raises(requests.Timeout) as raised:
        KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(today, today)

    assert raised.value is error
