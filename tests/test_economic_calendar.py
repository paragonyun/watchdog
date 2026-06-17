import pytest

from portfolio_watchdog.economic_calendar import build_economic_calendar_payload


def calendar_source() -> dict:
    return {
        "schema_version": "codex_economic_calendar_v1",
        "generated_at": "2026-06-18T08:00:00+09:00",
        "source": "codex",
        "timezone": "Asia/Seoul",
        "events": [
            {
                "id": "us-cpi-20260619",
                "title": "미국 CPI",
                "starts_at": "2026-06-19T21:30:00+09:00",
                "country": "미국",
                "category": "물가",
                "importance": "high",
                "asset_groups": ["isa", "coin"],
                "expected_impact": "인플레이션 경로에 따라 주식과 코인의 할인율 부담이 달라질 수 있습니다.",
                "watch_note": "근원 CPI와 서비스 물가를 확인합니다.",
                "source_url": "https://example.com/cpi",
            }
        ],
    }


def test_builds_privacy_safe_economic_calendar_payload() -> None:
    payload = build_economic_calendar_payload(calendar_source())

    assert payload["schema_version"] == "dashboard_calendar_v1"
    assert payload["events"][0]["importance"] == "high"
    assert payload["events"][0]["asset_groups"] == ["isa", "coin"]
    assert "quantity" not in str(payload)


def test_rejects_invalid_calendar_and_sensitive_fields() -> None:
    invalid = calendar_source()
    invalid["events"][0]["importance"] = "critical"
    with pytest.raises(ValueError, match="importance"):
        build_economic_calendar_payload(invalid)

    unsafe = calendar_source()
    unsafe["events"][0]["account_no"] = "123"
    with pytest.raises(ValueError, match="forbidden cloud field"):
        build_economic_calendar_payload(unsafe)
