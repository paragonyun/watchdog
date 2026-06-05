from datetime import datetime, timedelta

import pytest

from portfolio_watchdog.models import AssetEvaluation, NewsItem, PortfolioEvaluation
from portfolio_watchdog.report_data import build_portfolio_report_source, build_report_caption, build_report_payload
from portfolio_watchdog.report_validation import require_valid_report_payload, validate_report_payload


def test_report_payload_validates_current_api_values_and_trend() -> None:
    now = datetime(2026, 5, 16, 18, 5)
    portfolio = PortfolioEvaluation(
        assets=[
            AssetEvaluation(symbol="BTC", name="비트코인", asset_type="coin", target_weight=0.2, current_quantity=1, manual_value_krw=None, current_value_krw=200, current_weight=0.2),
            AssetEvaluation(symbol="SPY", name="S&P500", asset_type="equity", target_weight=0.7, current_quantity=1, manual_value_krw=700, current_value_krw=700, current_weight=0.7),
            AssetEvaluation(symbol="CASH", name="현금", asset_type="cash", target_weight=0.1, current_quantity=None, manual_value_krw=100, current_value_krw=100, current_weight=0.1),
        ],
        total_value_krw=1000,
    )
    history = {
        "portfolio_snapshots": [
            {
                "captured_at": (now - timedelta(hours=4)).isoformat(timespec="seconds"),
                "total_value_krw": 900,
                "asset_groups": {"coin": 180, "equity": 620, "cash": 100},
                "assets": [],
            }
        ],
        "news_items": [],
    }
    news = [NewsItem(title="비트코인 ETF 자금 유입", summary="", url="https://example.com", related_assets=["BTC"], impact="긍정", reason="BTC 관련")]

    payload = build_report_payload("portfolio", portfolio, history, news, generated_at=now, period_hours=6)

    assert payload["current_portfolio"]["total_value_krw"] == 1000
    assert payload["trend"]["change_krw"] == 100
    assert payload["validation"]["valid"] is True
    source = build_portfolio_report_source(payload)
    assert "포트폴리오 전문 PDF" in source
    assert "Public Equity 관점" in source
    assert "IB식 QC" in source
    assert "총자산 <b>1,000원</b>" in build_report_caption(tmp_path_like("portfolio_report_final_20260516_1805.pdf"), payload)


def test_report_payload_validation_rejects_bad_totals() -> None:
    payload = {
        "current_portfolio": {
            "total_value_krw": 1000,
            "asset_groups": {"coin": 100, "equity": 100, "cash": 100},
            "assets": [{"value_krw": 1000, "weight_percent": 100}],
        },
        "trend": {"start_total_krw": 900, "latest_total_krw": 1000, "change_krw": 1, "change_pct": 11.11},
        "news_impacts": [],
    }

    result = validate_report_payload(payload)

    assert result.valid is False
    with pytest.raises(ValueError, match="리포트 숫자 검증 실패"):
        require_valid_report_payload(payload)


def tmp_path_like(name: str):
    from pathlib import Path

    return Path(name)
