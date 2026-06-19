from portfolio_watchdog.dashboard_data import build_dashboard_payload


def test_dashboard_payload_preserves_news_source_metadata() -> None:
    payload = build_dashboard_payload(
        {
            "schema_version": 1,
            "report_kind": "portfolio",
            "generated_at": "2026-06-19T08:00:00",
            "current_portfolio": {
                "total_value_krw": 1000,
                "asset_groups": {"coin": 0, "equity": 1000, "cash": 0},
                "assets": [],
            },
            "trend": {},
            "news_impacts": [
                {
                    "title": "Market news",
                    "impact": "positive",
                    "impact_score": 2,
                    "related_assets": ["SPY"],
                    "reason": "Relevant to the portfolio.",
                    "why_it_matters": "Affects risk appetite.",
                    "url": "https://example.com/market-news",
                    "published_at": "2026-06-19T07:30:00+09:00",
                }
            ],
            "provider_status": [],
        }
    )

    assert payload["news_impacts"][0]["url"] == "https://example.com/market-news"
    assert payload["news_impacts"][0]["published_at"] == "2026-06-19T07:30:00+09:00"
