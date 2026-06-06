import pytest

import portfolio_watchdog.dashboard_data as dashboard_module
from portfolio_watchdog.cloud_contract import assert_cloud_safe
from portfolio_watchdog.dashboard_data import upload_dashboard_payload


FORBIDDEN_FIELDS = [
    "quantity",
    "current_quantity",
    "average_buy_price_krw",
    "account_no",
    "account_product_code",
    "order_id",
    "order_no",
    "uuid",
    "access_key",
    "api_key",
    "app_key",
    "secret_key",
    "app_secret",
    "raw_response",
    "raw_api_response",
]


@pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
def test_assert_cloud_safe_rejects_forbidden_fields_at_any_depth(field: str) -> None:
    payload = {"outer": [{"safe": True}, {field: "private"}]}

    with pytest.raises(ValueError, match=rf"^forbidden cloud field: \$\.outer\[1\]\.{field}$"):
        assert_cloud_safe(payload)


def test_assert_cloud_safe_compares_keys_in_lowercase() -> None:
    with pytest.raises(ValueError, match=r"^forbidden cloud field: \$\.API_KEY$"):
        assert_cloud_safe({"API_KEY": "private"})


def test_assert_cloud_safe_allows_safe_dashboard_payload_v2() -> None:
    payload = {
        "schema_version": "dashboard_payload_v2",
        "generated_at": "2026-06-06T08:00:00",
        "assets": [
            {
                "symbol": "BTC",
                "value_krw": 1000.0,
                "weight_percent": 100.0,
            }
        ],
        "provider_status": [{"provider": "upbit", "used_fallback": False}],
    }

    assert assert_cloud_safe(payload) is None


def test_upload_dashboard_payload_rejects_forbidden_fields_before_http_request(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(dashboard_module.requests, "post", lambda *args, **kwargs: calls.append((args, kwargs)))

    with pytest.raises(ValueError, match=r"^forbidden cloud field: \$\.assets\[0\]\.quantity$"):
        upload_dashboard_payload(
            {"schema_version": "dashboard_payload_v2", "assets": [{"quantity": 0.01}]},
            "https://example.com/api/upload",
            "upload-token",
        )

    assert calls == []
