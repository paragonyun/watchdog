from portfolio_watchdog.models import AssetEvaluation, NewsItem, PortfolioEvaluation
from portfolio_watchdog.reports import build_asset_status_report, build_news_report, build_portfolio_report


def _portfolio() -> PortfolioEvaluation:
    return PortfolioEvaluation(
        assets=[
            AssetEvaluation(symbol="BTC", name="Bitcoin", asset_type="coin", target_weight=0.5, current_quantity=1, manual_value_krw=None, current_value_krw=1000, current_weight=0.25, average_buy_price_krw=800, profit_loss_rate_pct=25),
            AssetEvaluation(symbol="TIGER_SP500", name="S&P", asset_type="equity", target_weight=0.5, current_quantity=1, manual_value_krw=3000, current_value_krw=3000, current_weight=0.75, average_buy_price_krw=2500, profit_loss_rate_pct=20),
        ],
        total_value_krw=4000,
    )


def test_portfolio_report_uses_html_and_escapes_news() -> None:
    news = [NewsItem(title="S&P500 <상승>", summary="", url="https://example.com/?a=1&b=2", related_assets=["TIGER_SP500"], impact="긍정", reason="금리 & 기술주")]
    report = build_portfolio_report(_portfolio(), [], news)
    assert "<b>Portfolio Watchdog 리포트</b>" in report
    assert "S&amp;P500 &lt;상승&gt;" in report
    assert "https://example.com/?a=1&amp;b=2" in report
    assert "긍정 1건" in report


def test_news_and_asset_status_reports_render() -> None:
    assert "뉴스 체크" in build_news_report([])
    assert "자산 변동 현황" in build_asset_status_report(_portfolio(), [])
