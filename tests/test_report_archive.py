from datetime import datetime

import pytest

from portfolio_watchdog.report_archive import build_report_archive_payload


def report_payload() -> dict:
    return {
        "schema_version": 1,
        "report_kind": "portfolio",
        "generated_at": datetime(2026, 6, 13, 9, 0).isoformat(timespec="seconds"),
        "current_portfolio": {
            "total_value_krw": 1_000,
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
        "trend": {
            "change_krw": 50,
            "change_pct": 5,
            "snapshot_count": 2,
        },
        "news_impacts": [],
        "provider_status": [
            {"provider": "upbit", "used_fallback": False, "error": "secret detail"}
        ],
        "validation": {"valid": True, "issues": []},
    }


def test_builds_privacy_safe_report_archive_payload() -> None:
    text = "\n".join(
        [
            "# 포트폴리오 리포트",
            "",
            "핵심 판단입니다.",
            "",
            "## 성과",
            "- 기간 수익률 +5.00%",
        ]
    )

    payload = build_report_archive_payload(
        text,
        report_payload(),
        "portfolio_report_final_20260613_0900.md",
    )

    assert payload["schema_version"] == "dashboard_report_v1"
    assert payload["report_id"] == "portfolio-20260613-0900"
    assert payload["document_status"] == "final"
    assert payload["summary"]["total_value_krw"] == 1_000
    assert payload["sections"] == [
        {"title": "포트폴리오 리포트", "lines": ["핵심 판단입니다."]},
        {"title": "성과", "lines": ["기간 수익률 +5.00%"]},
    ]
    assert payload["appendix"]["assets"][0]["symbol"] == "BTC"
    assert "quantity" not in str(payload)
    assert "average_buy_price_krw" not in str(payload)
    assert "secret detail" not in str(payload)


def test_parses_source_sections_and_rejects_sensitive_report_text() -> None:
    payload = build_report_archive_payload(
        "[현재 포트폴리오]\n- 총자산: 1,000원\n\n[검증 결과]\n- 통과",
        report_payload(),
        "portfolio_report_source_20260613_0900.txt",
    )

    assert payload["document_status"] == "source"
    assert [section["title"] for section in payload["sections"]] == [
        "현재 포트폴리오",
        "검증 결과",
    ]

    with pytest.raises(ValueError, match="민감 정보 표현"):
        build_report_archive_payload(
            "# 리포트\n- 수량: 0.01",
            report_payload(),
            "portfolio_report_final_20260613_0900.md",
        )
