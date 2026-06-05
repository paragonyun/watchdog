import json
from datetime import datetime

import pytest

import portfolio_watchdog.dashboard_data as dashboard_module
from portfolio_watchdog.dashboard_data import build_dashboard_payload, upload_dashboard_payload


def _report_payload() -> dict:
    return {
        "schema_version": 1,
        "report_kind": "portfolio",
        "generated_at": datetime(2026, 6, 5, 8, 0).isoformat(timespec="seconds"),
        "current_portfolio": {
            "total_value_krw": 1000,
            "asset_groups": {"coin": 200, "equity": 700, "cash": 100},
            "assets": [
                {
                    "symbol": "BTC",
                    "name": "비트코인",
                    "asset_type": "coin",
                    "value_krw": 200,
                    "weight_percent": 20,
                    "profit_loss_rate_percent": 10,
                    "quantity": 0.01,
                    "average_buy_price_krw": 150,
                    "price_source": "upbit",
                }
            ],
        },
        "trend": {"change_krw": 50, "change_pct": 5},
        "news_impacts": [
            {
                "title": "비트코인 ETF 자금 유입",
                "impact": "긍정",
                "impact_score": 2,
                "related_assets": ["BTC"],
                "reason": "비트코인 관련",
                "why_it_matters": "현재 비중과 연결됨",
                "url": "https://example.com/btc",
            }
        ],
        "provider_status": [
            {"provider": "upbit", "used_fallback": True, "error": "secret account detail"},
        ],
    }


def test_dashboard_payload_removes_sensitive_fields() -> None:
    payload = build_dashboard_payload(_report_payload())
    encoded = json.dumps(payload, ensure_ascii=False)

    assert payload["schema_version"] == "dashboard_payload_v1"
    assert payload["total_value_krw"] == 1000
    assert payload["assets"][0] == {
        "symbol": "BTC",
        "name": "비트코인",
        "asset_type": "coin",
        "value_krw": 200,
        "weight_percent": 20,
        "profit_loss_rate_percent": 10,
        "price_source": "upbit",
    }
    assert "quantity" not in encoded
    assert "average_buy_price_krw" not in encoded
    assert "secret account detail" not in encoded
    assert payload["provider_status"] == [{"provider": "upbit", "used_fallback": True}]


def test_upload_dashboard_payload_requires_endpoint_and_token() -> None:
    with pytest.raises(ValueError, match="WATCHDOG_DASHBOARD_UPLOAD_URL"):
        upload_dashboard_payload({}, "", "token")
    with pytest.raises(ValueError, match="WATCHDOG_UPLOAD_TOKEN"):
        upload_dashboard_payload({}, "https://example.com/api/upload", "")


def test_upload_dashboard_payload_sends_bearer_token(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(dashboard_module.requests, "post", lambda *args, **kwargs: calls.append((args, kwargs)) or Response())

    result = upload_dashboard_payload({"schema_version": "dashboard_payload_v1"}, "https://example.com/api/upload", "upload-token")

    assert result == {"ok": True}
    assert calls[0][1]["headers"]["Authorization"] == "Bearer upload-token"
    assert calls[0][1]["json"]["schema_version"] == "dashboard_payload_v1"
