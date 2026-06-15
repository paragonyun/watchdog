import pytest

from portfolio_watchdog.investment_opinion import build_investment_opinion_payload


def opinion_source() -> dict:
    return {
        "schema_version": "codex_investment_opinion_v1",
        "opinion_id": "opinion-20260615-1200",
        "generated_at": "2026-06-15T12:00:00+09:00",
        "portfolio_posture": "observe",
        "summary": "추가 매수보다 변동성 확인이 우선입니다.",
        "items": [
            {
                "id": "btc-observe",
                "symbol": "BTC",
                "name": "비트코인",
                "action": "observe",
                "confidence": "medium",
                "thesis": "유동성 회복 여부를 먼저 확인합니다.",
                "evidence": ["현 보유 비중이 목표 범위 상단입니다."],
                "counter_evidence": ["현물 ETF 자금 유입은 우호적입니다."],
                "catalysts": ["거래대금 회복"],
                "invalidation_conditions": ["ETF 순유출 확대"],
                "suggested_position_note": "신규 매수는 거래대금 회복 확인 후 검토",
                "sources": [{"label": "Codex 분석", "url": None}],
            }
        ],
        "disclaimer": "Codex 판단이며 투자 자문이나 자동 주문이 아닙니다.",
    }


def test_builds_privacy_safe_codex_opinion_payload() -> None:
    payload = build_investment_opinion_payload(opinion_source())

    assert payload["schema_version"] == "dashboard_opinion_v1"
    assert payload["items"][0]["action"] == "observe"
    assert payload["items"][0]["suggested_position_note"].startswith("신규 매수")
    assert "quantity" not in str(payload)


def test_rejects_non_codex_action_and_sensitive_fields() -> None:
    invalid = opinion_source()
    invalid["items"][0]["action"] = "maintain"
    with pytest.raises(ValueError, match="action"):
        build_investment_opinion_payload(invalid)

    unsafe = opinion_source()
    unsafe["items"][0]["quantity"] = 0.1
    with pytest.raises(ValueError, match="forbidden cloud field"):
        build_investment_opinion_payload(unsafe)
