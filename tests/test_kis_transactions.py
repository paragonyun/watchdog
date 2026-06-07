import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from portfolio_watchdog.providers import kis
from portfolio_watchdog.providers.kis import KisDomesticStockClient, parse_kis_daily_executions


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture() -> list[dict]:
    return json.loads((FIXTURES / "kis_daily_executions.json").read_text(encoding="utf-8"))


def test_parse_kis_daily_executions_maps_direction_time_and_fees() -> None:
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
        (120.0, -140120.0),
        (150.0, 70850.0),
        (0.0, -50000.0),
    ]
    assert events[0].occurred_at == datetime(2026, 5, 1, 0, 15, 30, tzinfo=timezone.utc)
    assert events[1].occurred_at == datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
    assert events[2].occurred_at == datetime(2026, 5, 3, 15, 0, tzinfo=timezone.utc)


def test_parse_kis_daily_executions_prefers_execution_time() -> None:
    row = {**_fixture()[0], "ord_tmd": "090000", "ccld_tmd": "101500"}

    event = parse_kis_daily_executions([row], {"005930": "SAMSUNG"})[0]

    assert event.occurred_at == datetime(2026, 5, 1, 1, 15, tzinfo=timezone.utc)


def test_parse_kis_daily_executions_rejects_unmapped_symbol() -> None:
    with pytest.raises(ValueError, match="005930"):
        parse_kis_daily_executions([_fixture()[0]], {})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tot_ccld_qty", "bad"),
        ("avg_prvs", "-1"),
        ("tot_ccld_amt", "139999"),
    ],
)
def test_parse_kis_daily_executions_validates_execution_totals(field, value) -> None:
    row = {**_fixture()[0], field: value}

    with pytest.raises(ValueError, match=field):
        parse_kis_daily_executions([row], {"005930": "SAMSUNG"})


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

    rows = KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions("20260501", "20260531")

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
        "INQR_STRT_DT": "20260501",
        "INQR_END_DT": "20260531",
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
        "EXCG_ID_DVSN_CD": "KRX",
    }
    assert calls[1][1]["params"]["CTX_AREA_FK100"] == "FK"
    assert calls[1][1]["params"]["CTX_AREA_NK100"] == "NK"
    assert all(call[1]["timeout"] == 10 for call in calls)


def test_kis_daily_executions_uses_virtual_tr_id(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(kis.requests, "get", lambda url, **kwargs: calls.append(kwargs) or Response({"output1": []}))

    KisDomesticStockClient(TokenClient("virtual"), "12345678", "01").get_daily_executions("20260501", "20260501")

    assert calls[0]["headers"]["tr_id"] == "VTTC0081R"


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("20260502", "20260501"),
        ("20260101", "20260402"),
        ("2026-05-01", "20260502"),
        ("2026051", "20260502"),
    ],
)
def test_kis_daily_executions_rejects_invalid_or_overlong_date_ranges_without_request(
    monkeypatch, start_date, end_date
) -> None:
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: pytest.fail("network called"))

    with pytest.raises(ValueError, match="date"):
        KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions(start_date, end_date)


def test_kis_daily_executions_validates_output_and_repeated_cursor(monkeypatch) -> None:
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: Response({"output1": {}}))
    client = KisDomesticStockClient(TokenClient(), "12345678", "01")
    with pytest.raises(ValueError, match="output1"):
        client.get_daily_executions("20260501", "20260501")

    monkeypatch.setattr(
        kis.requests,
        "get",
        lambda *args, **kwargs: Response(
            {"output1": [], "ctx_area_fk100": "SAME", "ctx_area_nk100": "SAME"},
            {"tr_cont": "M"},
        ),
    )
    with pytest.raises(RuntimeError, match="cursor"):
        client.get_daily_executions("20260501", "20260501")


def test_kis_daily_executions_propagates_request_errors(monkeypatch) -> None:
    error = requests.Timeout("private response detail")
    monkeypatch.setattr(kis.requests, "get", lambda *args, **kwargs: Response({}, error=error))

    with pytest.raises(requests.Timeout) as raised:
        KisDomesticStockClient(TokenClient(), "12345678", "01").get_daily_executions("20260501", "20260501")

    assert raised.value is error
