from portfolio_watchdog.models import AssetEvaluation, NewsItem, PortfolioEvaluation
from portfolio_watchdog.news_digest import cluster_news_items, write_hourly_codex_source
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


def test_news_report_clusters_similar_topics() -> None:
    news = [
        NewsItem(title="비트코인 1억2000만원 회복 - A", summary="", url="https://example.com/btc-a", related_assets=["BTC"], impact="긍정", reason="관련 키워드: 비트코인"),
        NewsItem(title="비트코인 상승세 지속 - B", summary="", url="https://example.com/btc-b", related_assets=["BTC"], impact="긍정", reason="관련 키워드: 비트코인"),
        NewsItem(title="미 국채 금리 급등 - C", summary="", related_assets=["ACE_US10Y_BOND_ACTIVE_H"], impact="부정", reason="관련 키워드: 금리"),
    ]
    topics = cluster_news_items(news)
    report = build_news_report(news)

    assert any(len(topic.items) == 2 and "BTC" in topic.related_assets for topic in topics)
    assert "핵심 이슈" in report
    assert "기사 2건" in report
    assert "관련 기사:" in report
    assert "https://example.com/btc-a" in report
    assert "확인 포인트" in report


def test_hourly_codex_source_created_for_important_news(tmp_path) -> None:
    news = [
        NewsItem(title="미 국채 금리 급등", summary="", url="https://example.com/rate", related_assets=["ACE_US10Y_BOND_ACTIVE_H"], impact="부정", reason="금리 급등"),
        NewsItem(title="나스닥 하락 반전", summary="", url="https://example.com/nasdaq", related_assets=["RISE_NASDAQ100"], impact="부정", reason="하락 반전"),
    ]

    path = write_hourly_codex_source(news, directory=str(tmp_path))

    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "텔레그램용 1시간 뉴스 고급 요약" in text
    assert "미 국채 금리 급등" in text
    assert "링크: https://example.com/rate" in text


def test_hourly_codex_source_not_created_for_normal_news(tmp_path) -> None:
    news = [
        NewsItem(title="시장 보합권 등락", summary="", related_assets=[], impact="중립", reason="방향: 중립"),
    ]

    assert write_hourly_codex_source(news, directory=str(tmp_path)) is None
