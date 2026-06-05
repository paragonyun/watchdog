from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .models import NewsItem, PortfolioEvaluation
from .news_digest import cluster_news_items
from .reports import _DISPLAY_NAMES
from .report_validation import validate_report_payload


@dataclass
class ReportArtifact:
    text_path: Path
    data_path: Path


_GROUP_LABELS = {"coin": "코인", "equity": "ISA", "cash": "현금"}


def build_report_payload(
    report_kind: str,
    portfolio: PortfolioEvaluation,
    history: Dict[str, Any],
    news_items: Sequence[NewsItem],
    generated_at: Optional[datetime] = None,
    period_days: Optional[int] = None,
    period_hours: Optional[int] = None,
    provider_status: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    now = generated_at or datetime.now()
    since = _period_start(now, period_days, period_hours, report_kind)
    current = _portfolio_snapshot(portfolio, now)
    snapshots = _recent_items(history.get("portfolio_snapshots", []), since)
    news_history = _recent_items(history.get("news_items", []), since)
    immediate_news = [_news_item_snapshot(item, now) for item in news_items]
    merged_news = _dedupe_news(news_history + immediate_news)
    trend = _build_trend(snapshots, current)
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "report_kind": report_kind,
        "generated_at": now.isoformat(timespec="seconds"),
        "period": {
            "start": since.isoformat(timespec="seconds"),
            "end": now.isoformat(timespec="seconds"),
            "days": period_days,
            "hours": period_hours,
        },
        "data_policy": {
            "current_values": "실행 시점 Upbit/KIS/가격 API 평가 결과 기준",
            "trend_values": "히스토리 스냅샷 기반",
            "unknown_policy": "확인되지 않은 사실은 확인 불가로 표시하고, 해석/추정은 라벨을 붙입니다.",
        },
        "provider_status": provider_status or [],
        "current_portfolio": current,
        "trend": trend,
        "snapshots": snapshots[-24:],
        "news_items": merged_news[-30:],
        "news_impacts": _news_impacts(merged_news[-30:], portfolio),
        "validation": {},
    }
    result = validate_report_payload(payload)
    payload["validation"] = {"valid": result.valid, "issues": result.issues}
    return payload


def build_portfolio_report_source(payload: Dict[str, Any]) -> str:
    current = payload["current_portfolio"]
    trend = payload["trend"]
    lines = [
        "아래 자료를 바탕으로 08/12/18 포트폴리오 전문 PDF 리포트를 작성해줘.",
        "",
        "[작성 원칙]",
        "- 확인된 숫자와 사실을 최우선으로 사용",
        "- 확인 불가능한 내용은 '확인 불가'로 표시",
        "- 해석은 'Codex 해석', 추정은 'Codex 추정'으로 명확히 라벨링",
        "- 직접적인 매수/매도/비중 조정 지시 금지",
        "- 최종 PDF는 짧은 텔레그램 캡션과 숫자가 일치해야 함",
        "- Public Equity 관점: 자산군 리스크, thesis 훼손 여부, catalyst/watch point를 분리",
        "- IB식 QC: 총자산/자산군/종목 합계, 단위, 날짜, 출처, 사실/해석/추정 라벨을 점검",
        "",
        "[기준]",
        f"- 기준 시각: {payload['generated_at']}",
        f"- 분석 기간: {payload['period']['start']} ~ {payload['period']['end']}",
        "- 현재 현황: 실행 시점 API 평가값",
        "- 추세: 히스토리 스냅샷 기반",
        "",
        "[현재 포트폴리오]",
        f"- 총자산: {_format_krw(current['total_value_krw'])}",
        *[
            f"- {_GROUP_LABELS[key]}: {_format_krw(value)} ({_format_weight(value, current['total_value_krw'])})"
            for key, value in current["asset_groups"].items()
        ],
        "",
        "[기간 변화]",
        f"- 시작 평가액: {_format_krw(trend.get('start_total_krw'))}",
        f"- 현재 평가액: {_format_krw(trend.get('latest_total_krw'))}",
        f"- 변화: {_format_krw(trend.get('change_krw'))} ({_format_pct(trend.get('change_pct'))})",
        "",
        "[종목별 현황]",
    ]
    lines.extend(_asset_lines(current["assets"]))
    lines.extend(["", "[주요 뉴스와 영향]"])
    lines.extend(_news_impact_lines(payload.get("news_impacts", [])))
    lines.extend(
        [
            "",
            "[Public Equity 관점 체크]",
            "- 포트폴리오 thesis에 긍정/부정/중립 영향을 주는 뉴스만 구분",
            "- 자산군별로 확인된 사실, Codex 해석, 확인 불가를 분리",
            "- 다음 관찰 포인트는 가격 지시가 아니라 재검토 조건으로 작성",
            "",
            "[IB식 QC 체크]",
            "- 모든 핵심 숫자는 위 구조화 JSON과 일치해야 함",
            "- 원화/퍼센트/기간 단위를 섞어 쓰지 말 것",
            "- 출처 없는 기관 전망이나 확정되지 않은 이벤트는 사실처럼 쓰지 말 것",
        ]
    )
    lines.extend(["", "[검증 결과]", *_validation_lines(payload)])
    return "\n".join(lines)


def build_weekly_report_source_from_payload(payload: Dict[str, Any]) -> str:
    current = payload["current_portfolio"]
    trend = payload["trend"]
    lines = [
        "아래 자료를 바탕으로 포트폴리오 위클리 전문 PDF 리포트를 작성해줘.",
        "",
        "[작성 원칙]",
        "- 사용자가 제공한 4페이지 샘플 양식과 깔끔한 증권사 리서치 스타일을 반영",
        "- 확인된 숫자와 사실을 최우선으로 사용",
        "- 확인 불가능한 내용은 '확인 불가'로 표시",
        "- 해석은 'Codex 해석', 추정은 'Codex 추정'으로 명확히 라벨링",
        "- 금융기관 전망은 공개 출처에서 확인한 경우에만 출처명/날짜와 함께 작성",
        "- 직접적인 매수/매도/비중 조정 지시 금지",
        "- Public Equity 관점: thesis, risk, catalyst, watch point를 구분",
        "- IB식 QC: 숫자 tie-out, 단위, 날짜, 출처, 사실/해석/추정 라벨을 확인",
        "",
        "[기준]",
        f"- 기준 시각: {payload['generated_at']}",
        f"- 분석 기간: {payload['period']['start']} ~ {payload['period']['end']}",
        "- 현재 현황: 실행 시점 API 평가값",
        "- 주간 추세: 히스토리 스냅샷 기반",
        "",
        "[현재 포트폴리오]",
        f"- 총자산: {_format_krw(current['total_value_krw'])}",
        *[
            f"- {_GROUP_LABELS[key]}: {_format_krw(value)} ({_format_weight(value, current['total_value_krw'])})"
            for key, value in current["asset_groups"].items()
        ],
        "",
        "[주간 평가액 추세]",
        f"- 시작: {trend.get('start_at') or '확인 불가'} / {_format_krw(trend.get('start_total_krw'))}",
        f"- 현재: {trend.get('latest_at') or payload['generated_at']} / {_format_krw(trend.get('latest_total_krw'))}",
        f"- 변화: {_format_krw(trend.get('change_krw'))} ({_format_pct(trend.get('change_pct'))})",
        f"- 스냅샷 수: {trend.get('snapshot_count', 0)}개",
        "",
        "[종목별 현황]",
    ]
    lines.extend(_asset_lines(current["assets"]))
    lines.extend(["", "[주요 뉴스와 영향]"])
    lines.extend(_news_impact_lines(payload.get("news_impacts", [])))
    lines.extend(
        [
            "",
            "[Public Equity 관점 체크]",
            "- 이번 주 thesis가 강화/유지/약화/확인 불가 중 어디에 가까운지 자산군별로 표시",
            "- catalyst/watch point는 다음 주 확인할 이벤트와 데이터로만 작성",
            "- 매수/매도 지시 대신 재검토 조건과 확인할 증거를 제시",
            "",
            "[IB식 QC 체크]",
            "- 총자산, 자산군 합계, 종목 합계, 변화율이 JSON과 일치하는지 확인",
            "- 같은 수치를 본문/표/캡션에서 다르게 쓰지 말 것",
            "- 확인된 사실, Codex 해석, Codex 추정을 문장마다 구분",
            "",
            "[금융기관 전망 작성 지시]",
            "- 실행 시점에 공개 웹 출처를 확인해 기관 전망을 요약",
            "- 확인 가능한 공개 출처가 없으면 '확인된 공개 전망 없음'으로 표시",
            "- 전망과 포트폴리오 영향 해석을 구분",
            "",
            "[검증 결과]",
            *_validation_lines(payload),
        ]
    )
    return "\n".join(lines)


def write_report_artifact(source: str, payload: Dict[str, Any], prefix: str, directory: str = "reports", now: Optional[datetime] = None) -> ReportArtifact:
    generated_at = now or _parse_datetime(payload.get("generated_at")) or datetime.now()
    base = Path(directory) / f"{prefix}_{generated_at:%Y%m%d_%H%M}"
    base.parent.mkdir(parents=True, exist_ok=True)
    text_path = base.with_suffix(".txt")
    data_path = base.with_suffix(".json")
    text_path.write_text(source, encoding="utf-8")
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ReportArtifact(text_path=text_path, data_path=data_path)


def find_report_payload_path(report_path: Path) -> Optional[Path]:
    path = Path(report_path)
    candidates = [path.with_suffix(".json")]
    match = re.search(r"(weekly|portfolio)_report_(?:final|source)_(\d{8}_\d{4})", path.name)
    if match:
        kind, stamp = match.groups()
        candidates.append(path.with_name(f"{kind}_report_source_{stamp}.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_report_payload_for_path(report_path: Path) -> Optional[Dict[str, Any]]:
    payload_path = find_report_payload_path(report_path)
    if payload_path is None:
        return None
    return json.loads(payload_path.read_text(encoding="utf-8"))


def build_report_caption(report_path: Path, payload: Optional[Dict[str, Any]] = None) -> str:
    payload = payload or load_report_payload_for_path(report_path)
    if not payload:
        return "\n".join(["<b>Portfolio Watchdog 리포트</b>", f"<code>{Path(report_path).name}</code>"])
    current = payload["current_portfolio"]
    trend = payload.get("trend") or {}
    title = "위클리 리포트" if payload.get("report_kind") == "weekly" else "포트폴리오 리포트"
    top_news = (payload.get("news_impacts") or [{}])[0]
    lines = [
        f"<b>Portfolio Watchdog {title}</b>",
        f"<code>{payload.get('generated_at')}</code>",
        f"총자산 <b>{_format_krw(current.get('total_value_krw'))}</b>",
        f"기간 변화 {html_escape_text(_format_krw(trend.get('change_krw')))} ({html_escape_text(_format_pct(trend.get('change_pct')))})",
    ]
    if top_news.get("title"):
        lines.append(f"대표 뉴스: {html_escape_text(str(top_news['title'])[:80])}")
    lines.append(f"첨부: <code>{Path(report_path).name}</code>")
    return "\n".join(lines)


def html_escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _portfolio_snapshot(portfolio: PortfolioEvaluation, captured_at: datetime) -> Dict[str, Any]:
    groups = {key: _sum_by_type(portfolio, key) for key in _GROUP_LABELS}
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "total_value_krw": round(portfolio.total_value_krw, 2),
        "asset_groups": groups,
        "assets": [_asset_snapshot(asset) for asset in portfolio.assets],
    }


def _asset_snapshot(asset) -> Dict[str, Any]:
    return {
        "symbol": asset.symbol,
        "name": _DISPLAY_NAMES.get(asset.symbol, asset.name or asset.symbol),
        "asset_type": asset.asset_type,
        "value_krw": round(asset.current_value_krw, 2),
        "weight_percent": round(asset.current_weight * 100, 4),
        "profit_loss_rate_percent": asset.profit_loss_rate_pct,
        "quantity": asset.current_quantity,
        "average_buy_price_krw": asset.average_buy_price_krw,
        "price_source": asset.price_quote.source if asset.price_quote else ("manual" if asset.manual_value_krw is not None else "unknown"),
    }


def _news_item_snapshot(item: NewsItem, captured_at: datetime) -> Dict[str, Any]:
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "published_at": item.published_at.isoformat(timespec="seconds") if item.published_at else None,
        "title": item.title,
        "source": item.source,
        "url": item.url,
        "related_assets": item.related_assets,
        "impact": item.impact,
        "reason": item.reason,
    }


def _news_impacts(news_items: Sequence[Dict[str, Any]], portfolio: PortfolioEvaluation) -> List[Dict[str, Any]]:
    converted = [
        NewsItem(
            title=str(item.get("title") or ""),
            summary="",
            source=str(item.get("source") or ""),
            url=item.get("url"),
            related_assets=list(item.get("related_assets") or []),
            impact=str(item.get("impact") or "중립"),
            reason=str(item.get("reason") or ""),
        )
        for item in news_items
    ]
    topics = cluster_news_items(converted)
    weights = {asset.symbol: asset.current_weight for asset in portfolio.assets}
    rows: List[Dict[str, Any]] = []
    for topic in topics[:8]:
        score = _impact_score(topic.impact, topic.related_assets, weights, len(topic.items), bool(topic.high_risk_keywords))
        rows.append(
            {
                "title": topic.title,
                "impact": topic.impact,
                "impact_score": score,
                "score_label": "Codex 해석",
                "related_assets": topic.related_assets,
                "reason": _topic_reason(topic.impact, topic.related_assets),
                "why_it_matters": "확인된 뉴스와 현재 포트폴리오 비중을 바탕으로 한 Codex 해석입니다.",
                "url": next((item.url for item in topic.items if item.url), None),
            }
        )
    return rows


def _impact_score(impact: str, related_assets: Sequence[str], weights: Dict[str, float], item_count: int, high_risk: bool) -> int:
    direction = 1 if impact == "긍정" else -1 if impact == "부정" else 0
    if direction == 0:
        return 0
    related_weight = sum(weights.get(symbol, 0.0) for symbol in related_assets)
    magnitude = 1
    if item_count >= 2 or high_risk:
        magnitude += 1
    if related_weight >= 0.15:
        magnitude += 1
    return direction * min(magnitude, 3)


def _topic_reason(impact: str, related_assets: Sequence[str]) -> str:
    assets = ", ".join(_DISPLAY_NAMES.get(symbol, symbol) for symbol in related_assets) or "시장 전반"
    if impact == "긍정":
        return f"{assets}에 우호적인 방향으로 해석될 수 있습니다."
    if impact == "부정":
        return f"{assets}의 단기 변동성 또는 심리 부담 요인입니다."
    return f"{assets}와 연결된 참고 뉴스이며 방향성은 확인 불가입니다."


def _period_start(now: datetime, period_days: Optional[int], period_hours: Optional[int], report_kind: str) -> datetime:
    if period_days is not None:
        return now - timedelta(days=period_days)
    if period_hours is not None:
        return now - timedelta(hours=period_hours)
    if report_kind == "weekly":
        return now - timedelta(days=7)
    return _default_intraday_start(now)


def _default_intraday_start(now: datetime) -> datetime:
    if 7 <= now.hour < 12:
        previous = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        return previous
    if 12 <= now.hour < 18:
        return now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now.hour >= 18:
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    return now - timedelta(hours=6)


def _build_trend(snapshots: List[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    if snapshots:
        first = snapshots[0]
        start_total = _as_float(first.get("total_value_krw"))
        start_at = first.get("captured_at")
    else:
        start_total = _as_float(current.get("total_value_krw"))
        start_at = current.get("captured_at")
    latest_total = _as_float(current.get("total_value_krw"))
    return {
        "start_at": start_at,
        "latest_at": current.get("captured_at"),
        "start_total_krw": round(start_total, 2),
        "latest_total_krw": round(latest_total, 2),
        "change_krw": round(latest_total - start_total, 2),
        "change_pct": None if start_total <= 0 else round((latest_total - start_total) / start_total * 100, 4),
        "snapshot_count": len(snapshots),
    }


def _recent_items(items: Sequence[Dict[str, Any]], since: datetime) -> List[Dict[str, Any]]:
    recent = [item for item in items if (_parse_datetime(item.get("captured_at")) or since) >= since]
    recent.sort(key=lambda item: item.get("captured_at") or "")
    return recent


def _dedupe_news(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = item.get("url") or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _asset_lines(assets: Sequence[Dict[str, Any]]) -> List[str]:
    return [
        f"- {item['name']}: 평가액 {_format_krw(item['value_krw'])}, 비중 {_format_pct(item['weight_percent'])}, 수익률 {_format_optional_pct(item.get('profit_loss_rate_percent'))}, 출처 {item.get('price_source', 'unknown')}"
        for item in assets
    ]


def _news_impact_lines(news_impacts: Sequence[Dict[str, Any]]) -> List[str]:
    if not news_impacts:
        return ["- 확인된 주요 뉴스 없음"]
    lines: List[str] = []
    for item in news_impacts:
        related = ", ".join(_DISPLAY_NAMES.get(symbol, symbol) for symbol in item.get("related_assets", [])) or "시장 전반"
        lines.append(f"- [{item.get('impact', '중립')}] {item.get('title', '')}")
        lines.append(f"  영향 강도: {item.get('impact_score', 0):+} ({item.get('score_label', 'Codex 해석')}) / 관련 자산: {related}")
        lines.append(f"  해석: {item.get('reason', '확인 불가')}")
        if item.get("url"):
            lines.append(f"  링크: {item['url']}")
    return lines


def _validation_lines(payload: Dict[str, Any]) -> List[str]:
    validation = payload.get("validation") or {}
    if validation.get("valid"):
        return ["- 숫자/비중/변화율 기본 검증 통과"]
    return [f"- 검증 실패: {issue}" for issue in validation.get("issues", [])]


def _sum_by_type(portfolio: PortfolioEvaluation, asset_type: str) -> float:
    return round(sum(asset.current_value_krw for asset in portfolio.assets if asset.asset_type == asset_type), 2)


def _format_krw(value: Any) -> str:
    return f"{_as_float(value):,.0f}원"


def _format_weight(value: Any, total: Any) -> str:
    total_value = _as_float(total)
    return "0.00%" if total_value <= 0 else f"{_as_float(value) / total_value * 100:.2f}%"


def _format_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{_as_float(value):+.2f}%"


def _format_optional_pct(value: Any) -> str:
    return "-" if value is None else _format_pct(value)


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
