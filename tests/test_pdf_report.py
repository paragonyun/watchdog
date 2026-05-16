from datetime import datetime, timedelta

import pytest

from portfolio_watchdog.pdf_report import render_weekly_report_pdf


def test_render_weekly_report_pdf_creates_pdf(tmp_path) -> None:
    markdown = tmp_path / "weekly_report_final_20260516_2010.md"
    markdown.write_text(
        "\n".join(
            [
                "# Portfolio Watchdog 위클리 리포트",
                "",
                "## 핵심 요약",
                "- 총 자산은 증가했습니다.",
                "- 코인은 변동성이 있었습니다.",
                "- 다음 주에는 금리를 확인합니다.",
                "",
                "## 다음 주 체크포인트 5개",
                "1. 비트코인 가격 확인",
            ]
        ),
        encoding="utf-8",
    )
    now = datetime(2026, 5, 16, 20, 10)
    history = {
        "portfolio_snapshots": [
            _snapshot(now - timedelta(days=6), 1000, {"coin": 300, "equity": 600, "cash": 100}),
            _snapshot(now, 1200, {"coin": 280, "equity": 800, "cash": 120}),
        ],
        "news_items": [{"impact": "긍정"}, {"impact": "부정"}, {"impact": "중립"}],
    }

    pdf = render_weekly_report_pdf(markdown, history)

    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.stat().st_size > 1000


def test_render_weekly_report_pdf_missing_file_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="완성 리포트 파일을 찾을 수 없습니다"):
        render_weekly_report_pdf(tmp_path / "missing.md", {})


def _snapshot(captured_at: datetime, total: float, groups: dict[str, float]) -> dict:
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "total_value_krw": total,
        "asset_groups": groups,
        "assets": [
            {"symbol": "BTC", "name": "비트코인", "value_krw": groups["coin"], "weight_percent": groups["coin"] / total * 100, "profit_loss_rate_percent": 10},
            {"symbol": "SPY", "name": "S&P500", "value_krw": groups["equity"], "weight_percent": groups["equity"] / total * 100, "profit_loss_rate_percent": 20},
            {"symbol": "CASH", "name": "현금", "value_krw": groups["cash"], "weight_percent": groups["cash"] / total * 100, "profit_loss_rate_percent": None},
        ],
    }
