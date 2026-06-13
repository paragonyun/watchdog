from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from .models import NewsItem, PortfolioEvaluation


_RISK_SIGNALS: Sequence[Tuple[str, str, Sequence[str], bool]] = (
    ("security", "해킹", ("해킹", "보안 사고", "탈취", "취약점 공격"), True),
    ("regulation", "규제", ("거래 제한", "거래제한", "규제", "금지", "당국 조사"), True),
    ("rates", "긴축", ("긴축", "금리 인상", "국채 금리 급등", "중앙은행 매파"), True),
    ("inflation", "인플레이션", ("인플레이션", "물가 급등", "CPI 급등"), True),
    ("fx", "환율", ("환율 급등", "환율 변동", "달러 강세", "통화 약세"), False),
    ("economy", "침체", ("경기 침체", "경기침체", "침체", "고용 악화", "실업 급증"), True),
    ("geopolitics", "지정학", ("지정학", "제재", "무역갈등", "무역 갈등", "전쟁"), True),
    ("liquidity", "유동성", ("유동성", "자금유출", "자금 유출", "신용위험", "신용 위험", "부도"), True),
    ("market", "급락", ("급락", "폭락"), True),
    ("market", "하락", ("하락", "약세", "둔화", "우려", "불안", "압박", "조정"), False),
)

_MARKET_GROUPS: Dict[str, Sequence[str]] = {
    "rates": ("coin", "isa"),
    "inflation": ("coin", "isa"),
    "fx": ("coin", "isa"),
    "economy": ("isa",),
    "regulation": ("coin", "isa"),
    "geopolitics": ("coin", "isa"),
    "liquidity": ("coin", "isa"),
    "market": ("coin", "isa"),
}

_PRIMARY_SOURCE_MARKERS = (
    "금융위원회",
    "금융감독원",
    "한국은행",
    "연방준비",
    "중앙은행",
    "정부",
    "공정거래위원회",
    "sec",
)
_PRIMARY_DOMAINS = (".go.kr", ".gov", "federalreserve.gov")
_MAJOR_NEWS_MARKERS = ("reuters", "bloomberg")
_CATEGORY_LABELS = {
    "security": "산업",
    "regulation": "규제",
    "rates": "금리",
    "inflation": "금리",
    "fx": "환율",
    "economy": "경기",
    "geopolitics": "지정학",
    "liquidity": "유동성",
    "market": "산업",
}


def stable_risk_id(topic: str, scope: str, assets: Sequence[str], asset_groups: Sequence[str]) -> str:
    normalized = "|".join(
        [
            "|".join(_normalize(part) for part in topic.split("|")),
            _normalize(scope),
            ",".join(sorted({_normalize(asset) for asset in assets})),
            ",".join(sorted({_normalize(group) for group in asset_groups})),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_news_risk_payload(
    items: Sequence[NewsItem],
    portfolio: PortfolioEvaluation,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or datetime.now(timezone.utc)
    portfolio_assets = {asset.symbol: asset for asset in portfolio.assets}
    portfolio_groups = {_payload_group(asset.asset_type) for asset in portfolio.assets}
    events: Dict[str, Dict[str, Any]] = {}

    for item in items:
        if item.impact == "긍정" or (
            item.published_at is not None
            and _comparable_datetime(item.published_at) < _comparable_datetime(now) - timedelta(hours=72)
        ):
            continue
        related_assets = sorted({symbol for symbol in item.related_assets if symbol in portfolio_assets})
        signal = _risk_signal(item)
        if signal is None:
            if item.impact != "부정" or not related_assets:
                continue
            signal = ("market", "부정", False)
        category, strongest_signal, strong = signal
        if related_assets:
            scope = "direct"
            related_groups = sorted({_payload_group(portfolio_assets[symbol].asset_type) for symbol in related_assets})
        else:
            scope = "market"
            related_groups = sorted(set(_MARKET_GROUPS.get(category, ())) & portfolio_groups)
            if not related_groups:
                continue

        topic = f"{category}|{strongest_signal}"
        risk_id = stable_risk_id(topic, scope, related_assets, related_groups)
        event = events.setdefault(
            risk_id,
            {
                "risk_id": risk_id,
                "scope": scope,
                "category": category,
                "signal": strongest_signal,
                "strong": strong,
                "related_assets": related_assets,
                "related_asset_groups": related_groups,
                "items": [],
            },
        )
        event["items"].append(item)

    risks = [_build_risk(event, portfolio_assets, now) for event in events.values()]
    risks.sort(key=lambda risk: (risk.pop("_score"), risk["related_asset_weight_pct"], risk["last_updated_at"]), reverse=True)
    return {
        "schema_version": "news_risk_payload_v1",
        "generated_at": now.isoformat(),
        "lookback_hours": 72,
        "rss_generated_at": now.isoformat(),
        "codex_generated_at": None,
        "status": "actual",
        "direct_risks": [risk for risk in risks if risk["scope"] == "direct"],
        "market_risks": [risk for risk in risks if risk["scope"] == "market"],
    }


def _build_risk(event: Dict[str, Any], portfolio_assets: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    items: List[NewsItem] = event["items"]
    dated_items = [item for item in items if item.published_at is not None]
    first_seen = min((_comparable_datetime(item.published_at) for item in dated_items), default=_comparable_datetime(now))
    last_updated = max((_comparable_datetime(item.published_at) for item in dated_items), default=_comparable_datetime(now))
    related_weight_pct = round(sum(portfolio_assets[symbol].current_weight for symbol in event["related_assets"]) * 100, 4)
    if event["scope"] == "market":
        related_weight_pct = round(
            sum(asset.current_weight for asset in portfolio_assets.values() if _payload_group(asset.asset_type) in event["related_asset_groups"]) * 100,
            4,
        )
    sources = {_normalize(item.source) for item in items if item.source.strip()}
    score, reasons = _priority_score(
        related_weight_pct=related_weight_pct,
        direct=event["scope"] == "direct",
        source_count=len(sources),
        article_count=len(items),
        source_quality=_source_quality(items),
        strong=event["strong"],
        fresh=last_updated >= _comparable_datetime(now) - timedelta(hours=24),
    )
    links = list(
        {
            item.url: {"title": item.title, "url": item.url}
            for item in items
            if _safe_http_url(item.url)
        }.values()
    )
    title = max(items, key=lambda item: _comparable_datetime(item.published_at)).title
    category_key = event["category"]
    return {
        "_score": score,
        "risk_id": event["risk_id"],
        "scope": event["scope"],
        "priority": _priority(score),
        "title": title,
        "category": _CATEGORY_LABELS[category_key],
        "source_type": ["rss_rule"],
        "facts": [f"{item.source}: {item.title}" for item in items],
        "potential_impact": _potential_impact(_CATEGORY_LABELS[category_key], event["related_asset_groups"]),
        "transmission_path": _transmission_path(category_key),
        "related_assets": event["related_assets"],
        "related_asset_groups": event["related_asset_groups"],
        "related_asset_weight_pct": related_weight_pct,
        "watch_indicators": _watch_indicators(category_key),
        "counter_evidence": [],
        "priority_reasons": reasons,
        "source_links": links,
        "first_seen_at": first_seen.isoformat(),
        "last_updated_at": last_updated.isoformat(),
        "freshness": _freshness(dated_items, last_updated, now),
        "change_reason": None,
    }


def _risk_signal(item: NewsItem) -> Optional[Tuple[str, str, bool]]:
    text = _normalize(f"{item.title} {item.summary} {item.reason}")
    matches: List[Tuple[str, str, bool]] = []
    for category, signal, keywords, strong in _RISK_SIGNALS:
        if any(_normalize(keyword) in text for keyword in keywords):
            matches.append((category, signal, strong))
    return max(matches, key=lambda match: match[2]) if matches else None


def _priority_score(
    *,
    related_weight_pct: float,
    direct: bool,
    source_count: int,
    article_count: int,
    source_quality: int,
    strong: bool,
    fresh: bool,
) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    if related_weight_pct >= 30:
        score += 3
        reasons.append("관련 비중 30% 이상 (+3)")
    elif related_weight_pct >= 15:
        score += 2
        reasons.append("관련 비중 15% 이상 (+2)")
    elif related_weight_pct > 0:
        score += 1
        reasons.append("포트폴리오 연결 비중 있음 (+1)")
    if direct:
        score += 2
        reasons.append("직접 관련 자산 (+2)")
    if source_count >= 3:
        score += 2
        reasons.append("독립 출처 3개 이상 (+2)")
    elif source_count == 2:
        score += 1
        reasons.append("독립 출처 2개 (+1)")
    else:
        reasons.append(f"독립 출처 {source_count}개")
    reasons.append(f"반복 기사 {article_count}건")
    if source_quality == 2:
        score += 2
        reasons.append("1차 출처 포함 (+2)")
    elif source_quality == 1:
        score += 1
        reasons.append("Reuters/Bloomberg 출처 포함 (+1)")
    score += 2 if strong else 1
    reasons.append("강한 위험 신호 (+2)" if strong else "일반 위험 신호 (+1)")
    if fresh:
        score += 1
        reasons.append("24시간 이내 신규 (+1)")
    return score, reasons


def _source_quality(items: Sequence[NewsItem]) -> int:
    for item in items:
        source = _normalize(item.source)
        host = urlparse(item.url or "").hostname or ""
        if any(marker in source for marker in _PRIMARY_SOURCE_MARKERS) or any(host.endswith(domain) for domain in _PRIMARY_DOMAINS):
            return 2
    if any(any(marker in _normalize(item.source) for marker in _MAJOR_NEWS_MARKERS) for item in items):
        return 1
    return 0


def _priority(score: int) -> str:
    if score >= 9:
        return "urgent"
    if score >= 5:
        return "caution"
    return "watch"


def _payload_group(asset_type: str) -> str:
    return "isa" if asset_type == "equity" else asset_type


def _safe_http_url(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _comparable_datetime(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _freshness(dated_items: Sequence[NewsItem], last_updated: datetime, now: datetime) -> str:
    if not dated_items:
        return "refresh_required"
    if last_updated >= _comparable_datetime(now) - timedelta(hours=24):
        return "new"
    return "active"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _potential_impact(category: str, groups: Sequence[str]) -> str:
    group_text = ", ".join(groups)
    return f"{category} 위험이 {group_text} 자산군의 가격 변동성과 손실 가능성을 높일 수 있습니다."


def _transmission_path(category: str) -> str:
    paths = {
        "security": "보안 신뢰 훼손 -> 거래 및 보유 심리 악화 -> 가격 변동성 확대",
        "regulation": "규제 강화 -> 거래 접근성 및 유동성 저하 -> 관련 자산 가격 압박",
        "rates": "긴축 및 금리 상승 -> 할인율 상승 -> 위험자산 가치 압박",
        "inflation": "물가 압력 -> 긴축 기대 강화 -> 위험자산 변동성 확대",
        "fx": "환율 변동 -> 원화 환산 가치 및 자금 흐름 변화 -> 포트폴리오 변동성 확대",
        "economy": "경기 둔화 -> 이익 및 위험선호 약화 -> 자산 가격 압박",
        "geopolitics": "지정학 갈등 -> 공급망 및 위험선호 악화 -> 시장 변동성 확대",
        "liquidity": "유동성 및 신용 악화 -> 강제 매도와 자금 조달 부담 -> 가격 하락 위험",
        "market": "시장 심리 악화 -> 매도 압력 증가 -> 가격 변동성 확대",
    }
    return paths[category]


def _watch_indicators(category: str) -> List[str]:
    indicators = {
        "security": ["사고 범위", "자금 회수 및 서비스 정상화"],
        "regulation": ["규제 시행 범위", "거래량 및 자금 흐름"],
        "rates": ["정책금리 기대", "국채 금리"],
        "inflation": ["CPI", "중앙은행 발언"],
        "fx": ["환율", "외국인 자금 흐름"],
        "economy": ["고용", "경기 선행지표"],
        "geopolitics": ["제재 범위", "무역 및 공급망 지표"],
        "liquidity": ["자금 유출", "신용 스프레드"],
        "market": ["가격 변동성", "거래량"],
    }
    return indicators[category]
