import re
from datetime import datetime, timedelta, timezone

from portfolio_watchdog.models import AssetEvaluation, NewsItem, PortfolioEvaluation
from portfolio_watchdog.news_analysis import risk_news_queries
from portfolio_watchdog.news_risk import build_news_risk_payload, stable_risk_id


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _portfolio() -> PortfolioEvaluation:
    return PortfolioEvaluation(
        assets=[
            AssetEvaluation(
                symbol="BTC",
                name="비트코인",
                asset_type="coin",
                target_weight=0.2,
                current_quantity=1,
                manual_value_krw=None,
                current_value_krw=200,
                current_weight=0.2,
            ),
            AssetEvaluation(
                symbol="TIGER_SP500",
                name="S&P500",
                asset_type="equity",
                target_weight=0.8,
                current_quantity=1,
                manual_value_krw=None,
                current_value_krw=800,
                current_weight=0.8,
            ),
        ],
        total_value_krw=1000,
    )


def _news(
    title: str,
    *,
    impact: str = "부정",
    related_assets: list[str] | None = None,
    source: str = "Example News",
    url: str = "https://example.com/news",
    hours_ago: int = 2,
) -> NewsItem:
    return NewsItem(
        title=title,
        summary="",
        source=source,
        url=url,
        published_at=NOW - timedelta(hours=hours_ago),
        related_assets=related_assets or [],
        impact=impact,
        reason="",
    )


def _score_from_reasons(reasons: list[str]) -> int:
    return sum(int(match.group(1)) for reason in reasons if (match := re.search(r"\(\+(\d+)\)", reason)))


def test_risk_news_queries_cover_required_market_risk_categories() -> None:
    queries = " ".join(risk_news_queries())

    for keyword in ["금리", "CPI", "환율", "침체", "고용", "가상자산 규제", "제재", "무역갈등", "유동성", "신용위험"]:
        assert keyword in queries


def test_build_payload_separates_direct_and_market_and_excludes_positive_news() -> None:
    payload = build_news_risk_payload(
        [
            _news("비트코인 거래 제한 규제 강화", related_assets=["BTC"]),
            _news("연준 긴축 장기화로 경기 둔화 우려", impact="중립", url="https://example.com/rates"),
            _news("비트코인 규제 완화 호재", impact="긍정", related_assets=["BTC"], url="https://example.com/good"),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    assert payload["schema_version"] == "news_risk_payload_v1"
    assert "schema" not in payload
    assert payload["generated_at"] == NOW.isoformat()
    assert payload["lookback_hours"] == 72
    assert payload["rss_generated_at"] == NOW.isoformat()
    assert payload["codex_generated_at"] is None
    assert payload["status"] == "actual"
    assert payload["direct_risks"][0]["related_assets"] == ["BTC"]
    assert payload["direct_risks"][0]["related_asset_groups"] == ["coin"]
    assert payload["market_risks"][0]["related_asset_groups"] == ["coin", "isa"]
    assert all(risk["title"] != "비트코인 규제 완화 호재" for risk in payload["direct_risks"] + payload["market_risks"])


def test_stable_id_normalizes_order_and_keeps_security_incident_separate() -> None:
    regulation_a = stable_risk_id("regulation|규제", "direct", ["BTC", "ETH"], ["coin"])
    regulation_b = stable_risk_id(" REGULATION | 규제 ", "DIRECT", ["ETH", "BTC"], ["COIN"])
    security = stable_risk_id("security|해킹", "direct", ["BTC", "ETH"], ["coin"])

    assert regulation_a == regulation_b
    assert len(regulation_a) == 16
    assert regulation_a != security


def test_event_merge_counts_independent_sources_and_records_score_reasons() -> None:
    payload = build_news_risk_payload(
        [
            _news("비트코인 거래 제한 규제 강화", related_assets=["BTC"], source="Reuters", url="https://reuters.com/a"),
            _news("당국, BTC 거래 규제 강화", related_assets=["BTC"], source="Bloomberg", url="https://bloomberg.com/b"),
            _news("비트코인 거래 규제 본격화", related_assets=["BTC"], source="금융위원회", url="https://fsc.go.kr/c"),
            _news("비트코인 거래 규제 본격화", related_assets=["BTC"], source="금융위원회", url="javascript:alert(1)"),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    risk = payload["direct_risks"][0]
    assert risk["priority"] == "urgent"
    assert risk["risk_id"] == stable_risk_id("regulation|규제", "direct", ["BTC"], ["coin"])
    assert "관련 비중 15% 이상 (+2)" in risk["priority_reasons"]
    assert "직접 관련 자산 (+2)" in risk["priority_reasons"]
    assert "독립 출처 3개 이상 (+2)" in risk["priority_reasons"]
    assert "반복 기사 4건 (+2)" in risk["priority_reasons"]
    assert "1차 출처 포함 (+2)" in risk["priority_reasons"]
    assert "강한 위험 신호 (+2)" in risk["priority_reasons"]
    assert "24시간 이내 신규 (+1)" in risk["priority_reasons"]
    assert len(risk["facts"]) == 4
    assert len(risk["source_links"]) == 3
    assert all(set(link) == {"title", "url"} for link in risk["source_links"])
    assert all(link["url"].startswith(("http://", "https://")) for link in risk["source_links"])


def test_repeated_articles_add_one_point_separately_from_independent_sources() -> None:
    repeated_payload = build_news_risk_payload(
        [
            _news("비트코인 거래 규제 강화", related_assets=["BTC"], url="https://example.com/a"),
            _news("BTC 거래 규제 본격화", related_assets=["BTC"], url="https://example.com/b"),
        ],
        _portfolio(),
        generated_at=NOW,
    )
    single_payload = build_news_risk_payload(
        [_news("비트코인 거래 규제 강화", related_assets=["BTC"], url="https://example.com/a")],
        _portfolio(),
        generated_at=NOW,
    )

    repeated = repeated_payload["direct_risks"][0]
    single = single_payload["direct_risks"][0]
    assert repeated["priority"] == single["priority"] == "caution"
    assert "반복 기사 2건 (+1)" in repeated["priority_reasons"]
    assert "독립 출처 1개" in repeated["priority_reasons"]
    assert _score_from_reasons(repeated["priority_reasons"]) == _score_from_reasons(single["priority_reasons"]) + 1


def test_contract_uses_allowed_categories_link_objects_and_freshness_values() -> None:
    payload = build_news_risk_payload(
        [
            _news("비트코인 거래 규제 강화", related_assets=["BTC"], url="https://example.com/new"),
            _news("S&P500 경기 침체 우려", related_assets=["TIGER_SP500"], url="https://example.com/active", hours_ago=25),
            NewsItem(
                title="비트코인 해킹 우려",
                summary="",
                source="Example News",
                url="https://example.com/undated",
                related_assets=["BTC"],
                impact="부정",
            ),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    risks = payload["direct_risks"]
    assert {risk["category"] for risk in risks} <= {"금리", "환율", "경기", "규제", "지정학", "유동성", "산업"}
    assert {risk["freshness"] for risk in risks} == {"new", "active", "refresh_required"}
    assert all(set(link) == {"title", "url"} for risk in risks for link in risk["source_links"])


def test_strongest_risk_signal_prefers_strong_match_over_earlier_general_match() -> None:
    payload = build_news_risk_payload(
        [_news("환율 변동 속 경기 침체 우려", related_assets=["TIGER_SP500"])],
        _portfolio(),
        generated_at=NOW,
    )

    risk = payload["direct_risks"][0]
    assert risk["category"] == "경기"
    assert risk["risk_id"] == stable_risk_id("economy|침체", "direct", ["TIGER_SP500"], ["isa"])
    assert "강한 위험 신호 (+2)" in risk["priority_reasons"]


def test_unconnected_news_is_excluded_and_equity_group_is_isa() -> None:
    payload = build_news_risk_payload(
        [
            _news("화산 폭발로 항공편 차질", url="https://example.com/volcano"),
            _news("S&P500 급락 우려", related_assets=["TIGER_SP500"], url="https://example.com/sp500"),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    assert len(payload["direct_risks"]) == 1
    assert payload["direct_risks"][0]["related_asset_groups"] == ["isa"]
    assert payload["market_risks"] == []


def test_market_risks_require_explainable_financial_or_held_group_evidence() -> None:
    payload = build_news_risk_payload(
        [
            _news("의약품 규제 강화", impact="중립", url="https://example.com/pharma"),
            _news("바이오 업종 급락", impact="중립", url="https://example.com/biotech"),
            _news("증시 급락", impact="중립", url="https://example.com/market"),
            _news("지정학 갈등 심화", impact="중립", url="https://example.com/geopolitics"),
            _news("가상자산 거래소 규제 강화", impact="중립", url="https://example.com/crypto"),
            _news("증권 거래 제한 규제 강화", impact="중립", url="https://example.com/securities"),
            _news("거래소 규제 강화", impact="중립", url="https://example.com/exchange"),
            _news("지정학 갈등으로 증시 변동성 확대", impact="중립", url="https://example.com/stocks"),
            _news("금융시장 유동성 악화", impact="중립", url="https://example.com/liquidity"),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    groups_by_title = {risk["title"]: risk["related_asset_groups"] for risk in payload["market_risks"]}
    assert "의약품 규제 강화" not in groups_by_title
    assert "바이오 업종 급락" not in groups_by_title
    assert groups_by_title["증시 급락"] == ["isa"]
    assert "지정학 갈등 심화" not in groups_by_title
    assert groups_by_title["가상자산 거래소 규제 강화"] == ["coin"]
    assert groups_by_title["증권 거래 제한 규제 강화"] == ["isa"]
    assert groups_by_title["거래소 규제 강화"] == ["coin", "isa"]
    assert groups_by_title["지정학 갈등으로 증시 변동성 확대"] == ["isa"]
    assert groups_by_title["금융시장 유동성 악화"] == ["coin", "isa"]


def test_direct_negative_news_is_candidate_without_keyword_and_old_news_is_excluded() -> None:
    payload = build_news_risk_payload(
        [
            _news("비트코인 사업 전망 악화", related_assets=["BTC"], url="https://example.com/negative"),
            _news("비트코인 해킹 우려", related_assets=["BTC"], url="https://example.com/old", hours_ago=73),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    assert len(payload["direct_risks"]) == 1
    assert payload["direct_risks"][0]["title"] == "비트코인 사업 전망 악화"


def test_risks_are_sorted_by_score_then_weight_then_latest_time() -> None:
    payload = build_news_risk_payload(
        [
            _news("비트코인 해킹 우려", related_assets=["BTC"], url="https://example.com/btc", hours_ago=1),
            _news("S&P500 하락 우려", related_assets=["TIGER_SP500"], url="https://example.com/sp500", hours_ago=3),
        ],
        _portfolio(),
        generated_at=NOW,
    )

    assert [risk["related_assets"] for risk in payload["direct_risks"]] == [["TIGER_SP500"], ["BTC"]]
