from datetime import datetime
from typing import Dict, List, Optional

from .message_format import html_escape
from .models import Alert, AssetEvaluation, NewsItem, PortfolioEvaluation

_DISPLAY_NAMES = {
    "BTC": "비트코인",
    "ETH": "이더리움",
    "LINK": "체인링크",
    "AAVE": "에이브",
    "ARB": "아비트럼",
    "RISE_NASDAQ100": "나스닥100",
    "TIGER_SP500": "S&P500",
    "TIGER_GOLD_FUTURES_H": "금 선물",
    "PLUS_HUMANOID_ROBOT": "휴머노이드 로봇",
    "SOL_US_NUCLEAR_SMR": "원자력/SMR",
    "KODEX_K_REIT_INFRA": "리츠/인프라",
    "ACE_US10Y_BOND_ACTIVE_H": "미국 10년 국채",
}
_SEPARATOR = "━━━━━━━━━━━━━━━━"


def build_portfolio_report(portfolio: PortfolioEvaluation, alerts: List[Alert], news_items: Optional[List[NewsItem]] = None) -> str:
    coin_total = _sum_by_type(portfolio.assets, "coin")
    isa_total = _sum_by_type(portfolio.assets, "equity")
    cash_total = _sum_by_type(portfolio.assets, "cash")
    news = news_items or []
    lines = [
        "<b>Portfolio Watchdog 리포트</b>",
        f"<code>{datetime.now():%Y-%m-%d %H:%M} 기준</code>",
        _SEPARATOR,
        "<b>총 자산 현황</b>",
        f"총 자산 <b>{_format_krw(portfolio.total_value_krw)}</b>",
        f"코인 {_format_krw(coin_total)} ({_format_weight(coin_total, portfolio.total_value_krw)}) / ISA {_format_krw(isa_total)} ({_format_weight(isa_total, portfolio.total_value_krw)}) / 현금 {_format_krw(cash_total)} ({_format_weight(cash_total, portfolio.total_value_krw)})",
        "",
        "<b>오늘 영향 뉴스</b>",
        _impact_summary(news),
    ]
    lines.extend(_build_news_lines(news, limit=3))
    lines.extend(["", _SEPARATOR, "<b>ISA 종목</b>"])
    lines.extend(_build_asset_lines(portfolio.assets, "equity"))
    lines.extend(["", "<b>코인</b>"])
    lines.extend(_build_asset_lines(portfolio.assets, "coin"))
    lines.extend(["", "<b>알림</b>"])
    lines.extend(_build_alert_lines(alerts))
    return "\n".join(lines)


def build_news_report(news_items: List[NewsItem]) -> str:
    lines = [
        "<b>Portfolio Watchdog 뉴스 체크</b>",
        f"<code>{datetime.now():%Y-%m-%d %H:%M} 기준</code>",
        _SEPARATOR,
        "<b>요약</b>",
        _impact_summary(news_items),
        "",
        "<b>중요 뉴스</b>",
    ]
    lines.extend(_build_news_lines(news_items, limit=8))
    return "\n".join(lines)


def build_asset_status_report(portfolio: PortfolioEvaluation, alerts: List[Alert]) -> str:
    coin_total = _sum_by_type(portfolio.assets, "coin")
    isa_total = _sum_by_type(portfolio.assets, "equity")
    cash_total = _sum_by_type(portfolio.assets, "cash")
    lines = [
        "<b>Portfolio Watchdog 자산 변동 현황</b>",
        f"<code>{datetime.now():%Y-%m-%d %H:%M} 기준</code>",
        _SEPARATOR,
        "<b>요약</b>",
        f"총 자산 <b>{_format_krw(portfolio.total_value_krw)}</b>",
        f"코인 {_format_krw(coin_total)} ({_format_weight(coin_total, portfolio.total_value_krw)}) / ISA {_format_krw(isa_total)} ({_format_weight(isa_total, portfolio.total_value_krw)}) / 현금 {_format_krw(cash_total)} ({_format_weight(cash_total, portfolio.total_value_krw)})",
        "",
        "<b>수익률 상위/하위</b>",
    ]
    lines.extend(_build_profit_rank_lines(portfolio.assets))
    lines.extend(["", "<b>알림</b>"])
    lines.extend(_build_alert_lines(alerts))
    return "\n".join(lines)


def _build_asset_lines(assets: List[AssetEvaluation], asset_type: str) -> List[str]:
    selected = [asset for asset in assets if asset.asset_type == asset_type]
    if not selected:
        return [f"등록된 {'ISA 종목' if asset_type == 'equity' else '코인'}이 없습니다."]
    lines: List[str] = []
    for index, asset in enumerate(selected, start=1):
        if index > 1:
            lines.append("")
        lines.extend(
            [
                f"<b>{index}. {html_escape(_display_name(asset))}</b>",
                f"평가액 {_format_krw(asset.current_value_krw)} / 비중 {asset.current_weight * 100:.2f}% / 수익률 {_format_optional_pct(asset.profit_loss_rate_pct)}",
                f"평단가 {_format_optional_krw(asset.average_buy_price_krw)}",
            ]
        )
    return lines


def _build_profit_rank_lines(assets: List[AssetEvaluation]) -> List[str]:
    ranked = [asset for asset in assets if asset.profit_loss_rate_pct is not None]
    ranked.sort(key=lambda asset: asset.profit_loss_rate_pct or 0, reverse=True)
    if not ranked:
        return ["수익률 데이터가 있는 자산이 없습니다."]
    selected = ranked[:3] + list(reversed(ranked[-3:]))
    lines: List[str] = []
    seen = set()
    for asset in selected:
        if asset.symbol in seen:
            continue
        seen.add(asset.symbol)
        lines.append(f"- {html_escape(_display_name(asset))}: {_format_optional_pct(asset.profit_loss_rate_pct)} / {_format_krw(asset.current_value_krw)} / 비중 {asset.current_weight * 100:.2f}%")
    return lines


def _build_news_lines(news_items: List[NewsItem], limit: int) -> List[str]:
    if not news_items:
        return ["오늘 포트폴리오 관련 주요 뉴스가 아직 없습니다."]
    lines: List[str] = []
    for index, item in enumerate(news_items[:limit], start=1):
        if index > 1:
            lines.append("")
        related = ", ".join(_display_symbol(symbol) for symbol in item.related_assets) or "시장 전반"
        lines.extend(
            [
                f"<b>{index}. {html_escape(item.title)}</b>",
                f"영향: <b>{html_escape(item.impact)}</b>",
                f"관련 자산: {html_escape(related)}",
                f"요약: {html_escape(item.reason or '추가 확인 필요')}",
            ]
        )
        if item.url:
            lines.append(f"링크: <a href=\"{html_escape(item.url, quote=True)}\">기사 보기</a>")
    return lines


def _build_alert_lines(alerts: List[Alert]) -> List[str]:
    if not alerts:
        return ["현재 알림 조건에 해당하는 변경 사항이 없습니다."]
    lines: List[str] = []
    for alert in alerts:
        lines.append(f"- <b>{html_escape(alert.title)}</b>")
        lines.append(html_escape(alert.message))
    return lines


def _impact_summary(news_items: List[NewsItem]) -> str:
    counts = _impact_counts(news_items)
    return f"부정 {counts['부정']}건 / 긍정 {counts['긍정']}건 / 중립 {counts['중립']}건"


def _impact_counts(news_items: List[NewsItem]) -> Dict[str, int]:
    counts = {"부정": 0, "긍정": 0, "중립": 0}
    for item in news_items:
        counts[item.impact if item.impact in counts else "중립"] += 1
    return counts


def _sum_by_type(assets: List[AssetEvaluation], asset_type: str) -> float:
    return sum(asset.current_value_krw for asset in assets if asset.asset_type == asset_type)


def _display_name(asset: AssetEvaluation) -> str:
    return _display_symbol(asset.symbol) or asset.name or asset.symbol


def _display_symbol(symbol: str) -> str:
    return _DISPLAY_NAMES.get(symbol, symbol)


def _format_weight(value: float, total: float) -> str:
    return "0.00%" if total <= 0 else f"{value / total * 100:.2f}%"


def _format_krw(value: float) -> str:
    return f"{value:,.0f}원"


def _format_optional_krw(value: Optional[float]) -> str:
    return "-" if value is None else _format_krw(value)


def _format_optional_pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:+.2f}%"
