import pytest

from portfolio_watchdog.research_report import build_research_report_payload


def research_report() -> dict:
    return {
        "schema_version": "dashboard_report_v2",
        "report_id": "portfolio-20260615-1200",
        "generated_at": "2026-06-15T12:00:00+09:00",
        "report_kind": "portfolio",
        "title": "포트폴리오 전략 리포트",
        "subtitle": "변동성 확대 구간, 현금과 확신을 함께 관리",
        "document_status": "final",
        "stance": "cautious",
        "summary": {
            "total_value_krw": 68_000_000,
            "change_krw": -200_000,
            "change_pct": -0.29,
            "validation_valid": True,
        },
        "executive_summary": [
            "ISA 비중이 포트폴리오의 중심입니다.",
            "코인은 변동성 확인 전 추가 매수를 유보합니다.",
        ],
        "key_metrics": [
            {"label": "누적 TWR", "value": "+8.4%", "context": "벤치마크 대비 +4.2%p", "tone": "positive"}
        ],
        "investment_thesis": {
            "headline": "핵심 자산은 유지하되 신규 위험 노출은 선별합니다.",
            "body": "포트폴리오의 수익 기여와 위험 집중도를 함께 평가했습니다.",
            "facts": ["ISA 비중 70% 내외"],
            "interpretations": ["주식시장 조정 시 전체 자산 변동성이 확대될 수 있습니다."],
            "estimates": ["현금 비중은 단기 완충 역할을 할 전망입니다."],
        },
        "asset_views": [
            {
                "symbol": "BTC",
                "name": "비트코인",
                "action": "observe",
                "thesis": "가격보다 유동성 확인이 우선입니다.",
                "catalysts": ["ETF 순유입 회복"],
                "risks": ["거래대금 감소"],
            }
        ],
        "scenarios": [
            {"name": "기준", "probability": "중간", "trigger": "금리 안정", "impact": "완만한 회복", "response": "현 비중 유지"}
        ],
        "risk_watchlist": ["코인 변동성 확대"],
        "conclusion": "확신이 높은 자산을 유지하고 현금 완충력을 보존합니다.",
        "appendix": {
            "asset_groups": {"coin": 11_000_000, "equity": 50_000_000, "cash": 7_000_000},
            "assets": [],
            "provider_status": [{"provider": "upbit", "used_fallback": False}],
            "validation_issues": [],
        },
    }


def test_accepts_completed_research_report() -> None:
    payload = build_research_report_payload(research_report())

    assert payload["schema_version"] == "dashboard_report_v2"
    assert payload["document_status"] == "final"
    assert payload["investment_thesis"]["facts"]


def test_rejects_prompt_like_or_sensitive_research_report() -> None:
    source = research_report()
    source["document_status"] = "source"
    with pytest.raises(ValueError, match="final"):
        build_research_report_payload(source)

    unsafe = research_report()
    unsafe["appendix"]["quantity"] = 1
    with pytest.raises(ValueError, match="forbidden cloud field"):
        build_research_report_payload(unsafe)
