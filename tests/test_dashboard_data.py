import json
from datetime import datetime

import pytest

import portfolio_watchdog.dashboard_data as dashboard_module
from portfolio_watchdog.cloud_contract import assert_cloud_safe
from portfolio_watchdog.dashboard_data import (
    build_dashboard_payload,
    build_dashboard_payload_v2,
    upload_dashboard_payload,
)


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


def test_dashboard_payload_v2_separates_return_and_allocation_and_filters_fields() -> None:
    summary = {
        "generated_at": "2026-06-06T08:00:00",
        "total_value_krw": 1_000_000,
        "data_freshness": {
            "portfolio_status": "actual",
            "last_actual_at": "2026-06-06T08:00:00",
            "reconciliation_status": "reconciled",
            "account_no": "private",
        },
        "performance": {
            "cumulative_twr_pct": 10.0,
            "month_twr_pct": 2.0,
            "benchmark_return_pct": 8.0,
            "excess_return_pct": 2.0,
            "max_drawdown_pct": -5.0,
            "status": "confirmed",
            "raw_response": "private",
        },
        "asset_groups": [
            {
                "asset_group": "equity",
                "value_krw": 600_000,
                "weight_percent": 60.0,
                "target_diff_percentage_points": 5.0,
                "profit_loss_rate_percent": 12.0,
                "quantity": 3,
            }
        ],
        "assets": [
            {
                "symbol": "SPY",
                "name": "S&P 500",
                "asset_type": "equity",
                "value_krw": 600_000,
                "weight_percent": 60.0,
                "target_diff_percentage_points": 5.0,
                "profit_loss_rate_percent": 12.0,
                "average_buy_price_krw": 400_000,
                "account_no": "private",
            }
        ],
        "provider_status": [
            {
                "provider": "kis",
                "status": "fallback",
                "used_fallback": True,
                "last_actual_at": "2026-06-06T07:59:00",
                "error": "secret detail",
                "raw_response": "private",
            }
        ],
        "trend": {"change_pct": 99},
    }

    payload = build_dashboard_payload_v2(summary)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert list(payload) == [
        "schema_version",
        "generated_at",
        "total_value_krw",
        "data_freshness",
        "performance",
        "asset_groups",
        "assets",
        "provider_status",
    ]
    assert payload["schema_version"] == "dashboard_payload_v2"
    assert payload["performance"]["cumulative_twr_pct"] == 10.0
    assert payload["asset_groups"] == [
        {
            "asset_group": "isa",
            "value_krw": 600_000,
            "weight_percent": 60.0,
            "target_diff_percentage_points": 5.0,
            "profit_loss_rate_percent": 12.0,
        }
    ]
    assert payload["assets"] == [
        {
            "symbol": "SPY",
            "name": "S&P 500",
            "asset_type": "isa",
            "value_krw": 600_000,
            "weight_percent": 60.0,
            "target_diff_percentage_points": 5.0,
            "profit_loss_rate_percent": 12.0,
        }
    ]
    assert payload["provider_status"] == [
        {
            "provider": "kis",
            "status": "fallback",
            "used_fallback": True,
            "last_actual_at": "2026-06-06T07:59:00",
        }
    ]
    assert "quantity" not in encoded
    assert "average_buy_price_krw" not in encoded
    assert "account_no" not in encoded
    assert "secret detail" not in encoded
    assert "trend" not in payload
    assert_cloud_safe(payload)


def test_dashboard_payload_v2_supports_legacy_asset_group_dict() -> None:
    payload = build_dashboard_payload_v2(
        {
            "asset_groups": {
                "coin": 200,
                "equity": {
                    "value_krw": 700,
                    "weight_percent": 70,
                    "quantity": 1,
                },
                "cash": 100,
            }
        }
    )

    assert payload["asset_groups"] == [
        {"asset_group": "coin", "value_krw": 200},
        {"asset_group": "isa", "value_krw": 700, "weight_percent": 70},
        {"asset_group": "cash", "value_krw": 100},
    ]


def test_dashboard_payload_v2_rejects_nested_value_in_allowed_field() -> None:
    with pytest.raises(ValueError, match="invalid dashboard v2 enum: status"):
        build_dashboard_payload_v2(
            {"provider_status": [{"provider": "kis", "status": {"error": "private"}}]}
        )


def test_dashboard_payload_v2_rejects_error_detail_in_status_field() -> None:
    with pytest.raises(ValueError, match="invalid dashboard v2 enum: status"):
        build_dashboard_payload_v2(
            {
                "provider_status": [
                    {"provider": "kis", "status": "account 123 raw failure"}
                ]
            }
        )


def test_dashboard_payload_v2_rejects_invalid_top_level_values() -> None:
    with pytest.raises(ValueError, match="generated_at"):
        build_dashboard_payload_v2({"generated_at": {"error": "private"}})
    with pytest.raises(ValueError, match="total_value_krw"):
        build_dashboard_payload_v2({"total_value_krw": float("nan")})
    with pytest.raises(ValueError, match="generated_at"):
        build_dashboard_payload_v2({"generated_at": "account 123 raw API error"})
    with pytest.raises(ValueError, match="last_actual_at"):
        build_dashboard_payload_v2(
            {"data_freshness": {"last_actual_at": "account 123 raw API error"}}
        )


def test_dashboard_payload_v2_validates_status_by_context() -> None:
    with pytest.raises(ValueError, match="invalid dashboard v2 enum: status"):
        build_dashboard_payload_v2({"performance": {"status": "error"}})
    with pytest.raises(ValueError, match="invalid dashboard v2 enum: status"):
        build_dashboard_payload_v2(
            {"provider_status": [{"provider": "kis", "status": "confirmed"}]}
        )
