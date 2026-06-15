import json

from portfolio_watchdog import app as app_module
from portfolio_watchdog.app import PortfolioWatchdogApp
from portfolio_watchdog.cli import build_parser

from test_weekly_report import _app_config


def test_parser_supports_sync_opinions() -> None:
    parser = build_parser()

    args = parser.parse_args(["sync-opinions", "--path", "opinion.json"])

    assert args.command == "sync-opinions"


def test_sync_opinions_uploads_codex_payload(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(
        _app_config(tmp_path),
        env={
            "WATCHDOG_DASHBOARD_UPLOAD_URL": "https://example.com/api/upload",
            "WATCHDOG_UPLOAD_TOKEN": "token",
        },
    )
    path = tmp_path / "opinion.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "codex_investment_opinion_v1",
                "opinion_id": "opinion-20260615-1200",
                "generated_at": "2026-06-15T12:00:00+09:00",
                "portfolio_posture": "observe",
                "summary": "변동성 확인이 우선입니다.",
                "items": [
                    {
                        "id": "btc-observe",
                        "symbol": "BTC",
                        "name": "비트코인",
                        "action": "observe",
                        "confidence": "medium",
                        "thesis": "유동성 회복 여부를 확인합니다.",
                        "evidence": ["비중이 목표 범위 상단입니다."],
                        "counter_evidence": ["ETF 자금 유입은 우호적입니다."],
                        "catalysts": ["거래대금 회복"],
                        "invalidation_conditions": ["ETF 순유출 확대"],
                        "suggested_position_note": "회복 확인 후 검토",
                        "sources": [{"label": "Codex 분석", "url": None}],
                    }
                ],
                "disclaimer": "Codex 판단이며 투자 자문이나 자동 주문이 아닙니다.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        app_module,
        "upload_dashboard_payload",
        lambda payload, endpoint, token: calls.append((payload, endpoint, token)) or {"ok": True},
    )

    payload = watchdog.sync_opinions(path)

    assert payload["schema_version"] == "dashboard_opinion_v1"
    assert calls[0][1:] == ("https://example.com/api/upload", "token")
