from datetime import datetime, timedelta

from portfolio_watchdog.models import AssetEvaluation, PortfolioEvaluation
from portfolio_watchdog.weekly_report import build_weekly_report_source, build_weekly_report_telegram_summary


def test_weekly_report_includes_trend(tmp_path) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    portfolio = PortfolioEvaluation(
        assets=[AssetEvaluation(symbol="BTC", name="Bitcoin", asset_type="coin", target_weight=1, current_quantity=1, manual_value_krw=None, current_value_krw=1100, current_weight=1, profit_loss_rate_pct=10)],
        total_value_krw=1100,
    )
    history = {"portfolio_snapshots": [{"captured_at": (now - timedelta(days=6)).isoformat(), "total_value_krw": 1000, "asset_groups": {"coin": 1000}}, {"captured_at": now.isoformat(), "total_value_krw": 1100, "asset_groups": {"coin": 1100}}], "news_items": []}
    source = build_weekly_report_source(portfolio, history, generated_at=now)
    summary = build_weekly_report_telegram_summary(portfolio, history, tmp_path / "weekly.txt", generated_at=now)
    assert "변화: 100원 (+10.00%)" in source
    assert "첨부된 txt 파일" in summary
