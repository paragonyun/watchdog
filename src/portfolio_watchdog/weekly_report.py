from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .message_format import html_escape
from .models import NewsItem, PortfolioEvaluation
from .reports import _DISPLAY_NAMES


def build_weekly_report_source(portfolio: PortfolioEvaluation, history: Dict[str, Any], generated_at: Optional[datetime] = None, days: int = 7) -> str:
    now = generated_at or datetime.now()
    since = now - timedelta(days=days)
    snapshots = _recent_items(history.get("portfolio_snapshots", []), since)
    news_items = _recent_items(history.get("news_items", []), since)
    lines = [
        "아래 자료를 바탕으로 내 포트폴리오 위클리 리포트를 만들어줘.",
        "",
        "[작성 조건]",
        "- 매수/매도 추천은 하지 말고, 자산별 영향과 관찰 포인트 중심으로 정리",
        "- 한국어로 간결하게 작성",
        "- 단기 영향과 중장기 영향을 구분",
        "- 마지막에 다음 주 체크할 포인트 5개 제시",
        "- 수익률/평가액 추세는 입출금 보정이 없는 단순 평가액 기준이라는 점을 감안",
        "",
        "[자료 기간]",
        f"- 기준 시각: {now:%Y-%m-%d %H:%M}",
        f"- 분석 기간: 최근 {days}일",
        "",
        "[현재 포트폴리오 요약]",
        f"- 총 자산: {_format_krw(portfolio.total_value_krw)}",
        f"- 코인: {_format_krw(_sum_by_type(portfolio.assets, 'coin'))}",
        f"- ISA: {_format_krw(_sum_by_type(portfolio.assets, 'equity'))}",
        f"- 현금: {_format_krw(_sum_by_type(portfolio.assets, 'cash'))}",
        "",
        "[주간 평가액 추세]",
    ]
    lines.extend(_build_total_trend_lines(snapshots))
    lines.extend(["", "[자산군별 주간 추세]"])
    lines.extend(_build_group_trend_lines(snapshots))
    lines.extend(["", "[현재 종목별 현황]"])
    lines.extend(_build_current_asset_lines(portfolio))
    lines.extend(["", "[이번 주 주요 뉴스 자료]"])
    lines.extend(_build_weekly_news_lines(news_items))
    lines.extend(["", "[리포트에서 특히 봐줬으면 하는 것]", "- 이번 주 내 포트폴리오에 가장 큰 영향을 준 요인", "- 코인, ISA, 현금 비중 관점의 리스크 변화", "- 다음 주에 확인할 금리/달러/코인/부동산/테마 뉴스"])
    return "\n".join(lines)


def write_weekly_report_source(report: str, directory: str = "reports", now: Optional[datetime] = None) -> Path:
    generated_at = now or datetime.now()
    path = Path(directory) / f"weekly_report_source_{generated_at:%Y%m%d_%H%M}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path


def build_weekly_report_telegram_summary(portfolio: PortfolioEvaluation, history: Dict[str, Any], report_path: Path, generated_at: Optional[datetime] = None, days: int = 7) -> str:
    now = generated_at or datetime.now()
    since = now - timedelta(days=days)
    snapshots = _recent_items(history.get("portfolio_snapshots", []), since)
    news_items = _recent_items(history.get("news_items", []), since)
    return "\n".join(
        [
            "<b>Portfolio Watchdog 위클리 리포트 자료</b>",
            f"<code>{now:%Y-%m-%d %H:%M} 기준</code>",
            "━━━━━━━━━━━━━━━━",
            "<b>요약</b>",
            f"총 자산 <b>{_format_krw(portfolio.total_value_krw)}</b>",
            f"주간 변화 {html_escape(_weekly_total_trend(snapshots))}",
            f"누적 뉴스 {len(news_items)}건",
            "",
            "<b>첨부 파일</b>",
            f"<code>{html_escape(report_path.name)}</code>",
            "첨부된 txt 파일 내용을 ChatGPT에 그대로 붙여넣으면 됩니다.",
        ]
    )


def news_item_to_history(item: NewsItem, captured_at: Optional[datetime] = None) -> Dict[str, Any]:
    now = captured_at or datetime.now()
    return {"captured_at": now.isoformat(timespec="seconds"), "published_at": item.published_at.isoformat(timespec="seconds") if item.published_at else None, "title": item.title, "source": item.source, "url": item.url, "related_assets": item.related_assets, "impact": item.impact, "reason": item.reason}


def _build_total_trend_lines(snapshots: List[Dict[str, Any]]) -> List[str]:
    if len(snapshots) < 2:
        return ["- 아직 주간 추세를 계산할 만큼 포트폴리오 스냅샷이 충분하지 않습니다."]
    first, latest = snapshots[0], snapshots[-1]
    first_total, latest_total = _as_float(first.get("total_value_krw")), _as_float(latest.get("total_value_krw"))
    lines = [
        f"- 시작: {_format_datetime(first.get('captured_at'))} / {_format_krw(first_total)}",
        f"- 현재: {_format_datetime(latest.get('captured_at'))} / {_format_krw(latest_total)}",
        f"- 변화: {_format_krw(latest_total - first_total)} ({_format_pct(_pct_change(first_total, latest_total))})",
        f"- 스냅샷 수: {len(snapshots)}개",
        "- 주간 포인트:",
    ]
    lines.extend([f"  - {_format_datetime(item.get('captured_at'))}: {_format_krw(_as_float(item.get('total_value_krw')))}" for item in snapshots[-10:]])
    return lines


def _build_group_trend_lines(snapshots: List[Dict[str, Any]]) -> List[str]:
    if len(snapshots) < 2:
        return ["- 아직 자산군별 추세 데이터가 충분하지 않습니다."]
    first_groups = snapshots[0].get("asset_groups", {}) or {}
    latest_groups = snapshots[-1].get("asset_groups", {}) or {}
    labels = {"coin": "코인", "equity": "ISA", "cash": "현금"}
    return [f"- {label}: {_format_krw(_as_float(first_groups.get(key)))} -> {_format_krw(_as_float(latest_groups.get(key)))} ({_format_pct(_pct_change(_as_float(first_groups.get(key)), _as_float(latest_groups.get(key))))})" for key, label in labels.items()]


def _build_current_asset_lines(portfolio: PortfolioEvaluation) -> List[str]:
    return [f"- {_display_name(asset.symbol, asset.name)}: 평가액 {_format_krw(asset.current_value_krw)}, 비중 {asset.current_weight * 100:.2f}%, 수익률 {_format_optional_pct(asset.profit_loss_rate_pct)}" for asset in portfolio.assets] or ["- 등록된 자산이 없습니다."]


def _build_weekly_news_lines(news_items: List[Dict[str, Any]]) -> List[str]:
    if not news_items:
        return ["- 이번 주 누적된 뉴스 자료가 아직 없습니다."]
    lines: List[str] = []
    for index, item in enumerate(news_items[-20:], start=1):
        related = ", ".join(_display_name(symbol, symbol) for symbol in item.get("related_assets", [])) or "시장 전반"
        lines.extend([f"{index}. [{item.get('impact', '중립')}] {item.get('title', '')}", f"   관련 자산: {related}", f"   영향 요약: {item.get('reason') or '추가 확인 필요'}"])
        if item.get("url"):
            lines.append(f"   링크: {item.get('url')}")
    return lines


def _weekly_total_trend(snapshots: List[Dict[str, Any]]) -> str:
    if len(snapshots) < 2:
        return "데이터 부족"
    first, latest = _as_float(snapshots[0].get("total_value_krw")), _as_float(snapshots[-1].get("total_value_krw"))
    return f"{_format_krw(latest - first)} ({_format_pct(_pct_change(first, latest))})"


def _recent_items(items: List[Dict[str, Any]], since: datetime) -> List[Dict[str, Any]]:
    recent = [item for item in items if (_parse_datetime(item.get("captured_at")) or since) >= since]
    recent.sort(key=lambda item: item.get("captured_at") or "")
    return recent


def _display_name(symbol: str, fallback: str) -> str:
    return _DISPLAY_NAMES.get(symbol, fallback or symbol)


def _sum_by_type(assets, asset_type: str) -> float:
    return sum(asset.current_value_krw for asset in assets if asset.asset_type == asset_type)


def _pct_change(first: float, latest: float) -> Optional[float]:
    return None if first <= 0 else (latest - first) / first * 100


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_datetime(value: Any) -> str:
    parsed = _parse_datetime(value)
    return "-" if parsed is None else f"{parsed:%Y-%m-%d %H:%M}"


def _format_krw(value: float) -> str:
    return f"{value:,.0f}원"


def _format_pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:+.2f}%"


def _format_optional_pct(value: Optional[float]) -> str:
    return "-" if value is None else _format_pct(value)
