from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from .cloud_contract import assert_cloud_safe
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

_COIN_MARKET_KEYWORDS = ("가상자산", "암호화폐", "비트코인", "이더리움", "코인", "디파이")
_ISA_MARKET_KEYWORDS = ("증권", "주식", "증시", "채권", "국채", "ETF", "나스닥", "S&P", "리츠")
_BROAD_FINANCIAL_KEYWORDS = ("금융시장", "금융 시스템", "신용위험", "신용 위험", "자금유출", "자금 유출")
_RATE_MARKET_KEYWORDS = ("금리", "국채", "채권", "중앙은행", "연준", "긴축")
_FX_MARKET_KEYWORDS = ("환율", "달러", "통화 약세")

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
_ALLOWED_CATEGORIES = {"금리", "환율", "경기", "규제", "지정학", "유동성", "산업"}
_ALLOWED_GROUPS = {"isa", "coin", "cash"}
_PRIORITY_RANK = {"urgent": 3, "caution": 2, "watch": 1}


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
            related_groups = _market_groups(category, item, portfolio_groups)
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


def merge_codex_news_risks(
    base_payload: dict[str, Any],
    codex_payload: dict[str, Any],
    portfolio: PortfolioEvaluation,
    merged_at: datetime | None = None,
) -> dict[str, Any]:
    validate_news_risk_payload(base_payload)
    validate_codex_news_risk_payload(codex_payload)
    now = _comparable_datetime(merged_at or datetime.now(timezone.utc))
    codex_generated_at = _parse_iso_datetime(codex_payload["generated_at"])
    stale_codex = codex_generated_at < now - timedelta(hours=72)
    result = copy.deepcopy(base_payload)
    portfolio_assets = {asset.symbol: asset for asset in portfolio.assets}
    portfolio_groups = {_payload_group(asset.asset_type) for asset in portfolio.assets}
    by_id = {
        risk["risk_id"]: risk
        for risk in result["direct_risks"] + result["market_risks"]
    }

    for codex_risk in codex_payload["risks"]:
        risk_id = codex_risk["risk_id"]
        if risk_id is not None:
            existing = by_id.get(risk_id)
            if existing is None:
                raise ValueError(f"unknown Codex risk_id: {risk_id}")
            _merge_existing_codex_risk(existing, codex_risk, codex_generated_at, stale_codex)
            continue

        new_risk = _build_codex_risk(
            codex_risk,
            portfolio_assets,
            portfolio_groups,
            codex_generated_at,
            stale_codex,
            now,
        )
        by_id[new_risk["risk_id"]] = new_risk
        result[f"{new_risk['scope']}_risks"].append(new_risk)

    result["generated_at"] = now.isoformat()
    result["codex_generated_at"] = codex_generated_at.isoformat()
    if result["status"] != "delayed":
        result["status"] = "refresh_required" if stale_codex else "actual"
    result["direct_risks"] = sorted(result["direct_risks"], key=_risk_sort_key, reverse=True)
    result["market_risks"] = sorted(result["market_risks"], key=_risk_sort_key, reverse=True)
    validate_news_risk_payload(result)
    return result


def load_json_object(path: Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"JSON 파일을 찾을 수 없습니다: {source}")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 최상위 값은 객체여야 합니다: {source}")
    return value


def validate_news_risk_payload(payload: dict[str, Any]) -> None:
    assert_cloud_safe(payload)
    if not isinstance(payload, dict) or payload.get("schema_version") != "news_risk_payload_v1":
        raise ValueError("news risk payload must use news_risk_payload_v1")
    _require_iso_datetime(payload.get("generated_at"), "generated_at")
    if payload.get("lookback_hours") != 72:
        raise ValueError("news risk lookback_hours must be 72")
    for field in ("rss_generated_at", "codex_generated_at"):
        if payload.get(field) is not None:
            _require_iso_datetime(payload[field], field)
    if payload.get("status") not in {"actual", "delayed", "refresh_required"}:
        raise ValueError("invalid news risk status")
    for field, scope in (("direct_risks", "direct"), ("market_risks", "market")):
        risks = payload.get(field)
        if not isinstance(risks, list):
            raise ValueError(f"{field} must be a list")
        for risk in risks:
            _validate_news_risk_item(risk, expected_scope=scope)


def validate_codex_news_risk_payload(payload: dict[str, Any]) -> None:
    assert_cloud_safe(payload)
    if not isinstance(payload, dict) or payload.get("schema_version") != "codex_news_risk_v1":
        raise ValueError("Codex payload must use codex_news_risk_v1")
    _require_iso_datetime(payload.get("generated_at"), "generated_at")
    risks = payload.get("risks")
    if not isinstance(risks, list):
        raise ValueError("Codex risks must be a list")
    for risk in risks:
        if not isinstance(risk, dict):
            raise ValueError("Codex risk must be an object")
        if risk.get("risk_id") is not None and not isinstance(risk.get("risk_id"), str):
            raise ValueError("Codex risk_id must be a string or null")
        scope = risk.get("scope")
        if scope not in {"direct", "market"}:
            raise ValueError("invalid Codex risk scope")
        for field in ("title", "potential_impact", "transmission_path"):
            _require_non_empty_string(risk.get(field), field)
        if risk.get("category") not in _ALLOWED_CATEGORIES:
            raise ValueError("invalid Codex risk category")
        for field in ("facts", "related_assets", "related_asset_groups", "watch_indicators", "counter_evidence"):
            _require_string_list(risk.get(field), field)
        if not set(risk["related_asset_groups"]) <= _ALLOWED_GROUPS:
            raise ValueError("invalid Codex risk asset group")
        _require_source_links(risk.get("source_links"), allow_unsafe=True)
        if risk.get("change_reason") is not None and not isinstance(risk.get("change_reason"), str):
            raise ValueError("Codex change_reason must be a string or null")
        if scope == "direct" and not risk["related_assets"]:
            raise ValueError("direct Codex risk related_assets must not be empty")
        if scope == "market" and not risk["related_asset_groups"]:
            raise ValueError("market Codex risk related_asset_groups must not be empty")


def save_news_risk_payload(payload: dict[str, Any], path: Path) -> None:
    validate_news_risk_payload(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _merge_existing_codex_risk(
    existing: dict[str, Any],
    codex_risk: dict[str, Any],
    generated_at: datetime,
    stale: bool,
) -> None:
    if (
        existing["scope"] != codex_risk["scope"]
        or set(existing["related_assets"]) != set(codex_risk["related_assets"])
        or set(existing["related_asset_groups"]) != set(codex_risk["related_asset_groups"])
    ):
        raise ValueError(f"Codex risk identity does not match existing risk_id: {existing['risk_id']}")
    interpretation_changed = any(
        existing[field] != codex_risk[field]
        for field in ("title", "category", "potential_impact", "transmission_path")
    )
    if interpretation_changed and not str(codex_risk.get("change_reason") or "").strip():
        raise ValueError("Codex interpretation change requires change_reason")
    for field in (
        "title",
        "category",
        "facts",
        "potential_impact",
        "transmission_path",
        "watch_indicators",
        "counter_evidence",
        "change_reason",
    ):
        existing[field] = copy.deepcopy(codex_risk[field])
    existing["source_type"] = sorted(set(existing["source_type"]) | {"codex_research"})
    existing["source_links"] = _safe_source_links([*existing["source_links"], *codex_risk["source_links"]])
    existing["last_updated_at"] = generated_at.isoformat()
    existing["freshness"] = "refresh_required" if stale else "new"


def _build_codex_risk(
    codex_risk: dict[str, Any],
    portfolio_assets: dict[str, Any],
    portfolio_groups: set[str],
    generated_at: datetime,
    stale: bool,
    now: datetime,
) -> dict[str, Any]:
    related_assets = sorted(set(codex_risk["related_assets"]) & set(portfolio_assets))
    related_groups = sorted(set(codex_risk["related_asset_groups"]) & portfolio_groups)
    if codex_risk["scope"] == "direct":
        if not related_assets:
            raise ValueError("Codex risk has no portfolio connection")
        expected_groups = sorted({_payload_group(portfolio_assets[symbol].asset_type) for symbol in related_assets})
        if related_groups != expected_groups:
            raise ValueError("Codex direct risk asset groups do not match portfolio")
    elif not related_groups:
        raise ValueError("Codex risk has no portfolio connection")

    related_weight_pct = round(
        sum(
            asset.current_weight
            for asset in portfolio_assets.values()
            if asset.symbol in related_assets
            or (codex_risk["scope"] == "market" and _payload_group(asset.asset_type) in related_groups)
        )
        * 100,
        4,
    )
    links = _safe_source_links(codex_risk["source_links"])
    sources = [
        NewsItem(title=link["title"], summary="", source=link["title"], url=link["url"])
        for link in links
    ]
    score, reasons = _priority_score(
        related_weight_pct=related_weight_pct,
        direct=codex_risk["scope"] == "direct",
        source_count=len({urlparse(link["url"]).hostname for link in links}),
        article_count=max(1, len(links)),
        source_quality=_source_quality(sources),
        strong=True,
        fresh=generated_at >= now - timedelta(hours=24),
    )
    risk_id = stable_risk_id(
        f"{codex_risk['category']}|{codex_risk['title']}",
        codex_risk["scope"],
        related_assets,
        related_groups,
    )
    return {
        "risk_id": risk_id,
        "scope": codex_risk["scope"],
        "priority": _priority(score),
        "title": codex_risk["title"],
        "category": codex_risk["category"],
        "source_type": ["codex_research"],
        "facts": copy.deepcopy(codex_risk["facts"]),
        "potential_impact": codex_risk["potential_impact"],
        "transmission_path": codex_risk["transmission_path"],
        "related_assets": related_assets,
        "related_asset_groups": related_groups,
        "related_asset_weight_pct": related_weight_pct,
        "watch_indicators": copy.deepcopy(codex_risk["watch_indicators"]),
        "counter_evidence": copy.deepcopy(codex_risk["counter_evidence"]),
        "priority_reasons": reasons,
        "source_links": links,
        "first_seen_at": generated_at.isoformat(),
        "last_updated_at": generated_at.isoformat(),
        "freshness": "refresh_required" if stale else ("new" if generated_at >= now - timedelta(hours=24) else "active"),
        "change_reason": codex_risk["change_reason"],
    }


def _validate_news_risk_item(risk: Any, expected_scope: str) -> None:
    if not isinstance(risk, dict):
        raise ValueError("news risk item must be an object")
    if risk.get("scope") != expected_scope:
        raise ValueError("news risk item scope does not match its collection")
    _require_non_empty_string(risk.get("risk_id"), "risk_id")
    _require_non_empty_string(risk.get("title"), "title")
    if risk.get("priority") not in _PRIORITY_RANK:
        raise ValueError("invalid news risk priority")
    if risk.get("category") not in _ALLOWED_CATEGORIES:
        raise ValueError("invalid news risk category")
    if risk.get("freshness") not in {"new", "active", "refresh_required"}:
        raise ValueError("invalid news risk freshness")
    for field in (
        "source_type",
        "facts",
        "related_assets",
        "related_asset_groups",
        "watch_indicators",
        "counter_evidence",
        "priority_reasons",
    ):
        _require_string_list(risk.get(field), field)
    if not set(risk["source_type"]) <= {"rss_rule", "codex_research"}:
        raise ValueError("invalid news risk source_type")
    if not set(risk["related_asset_groups"]) <= _ALLOWED_GROUPS:
        raise ValueError("invalid news risk asset group")
    for field in ("potential_impact", "transmission_path"):
        _require_non_empty_string(risk.get(field), field)
    weight = risk.get("related_asset_weight_pct")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
        raise ValueError("related_asset_weight_pct must be a finite number")
    _require_source_links(risk.get("source_links"), allow_unsafe=False)
    _require_iso_datetime(risk.get("first_seen_at"), "first_seen_at")
    _require_iso_datetime(risk.get("last_updated_at"), "last_updated_at")
    if risk.get("change_reason") is not None and not isinstance(risk.get("change_reason"), str):
        raise ValueError("change_reason must be a string or null")


def _require_string_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a string list")


def _require_source_links(value: Any, allow_unsafe: bool) -> None:
    if not isinstance(value, list):
        raise ValueError("source_links must be a list")
    for link in value:
        if not isinstance(link, dict) or set(link) != {"title", "url"}:
            raise ValueError("source_links entries must contain title and url")
        _require_non_empty_string(link["title"], "source link title")
        _require_non_empty_string(link["url"], "source link url")
        if not allow_unsafe and not _safe_external_http_url(link["url"]):
            raise ValueError("unsafe source link URL")


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _require_iso_datetime(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    _parse_iso_datetime(value)


def _parse_iso_datetime(value: str) -> datetime:
    try:
        return _comparable_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {value}") from exc


def _safe_source_links(links: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links:
        url = link["url"]
        if url in seen or not _safe_external_http_url(url):
            continue
        seen.add(url)
        result.append({"title": link["title"], "url": url})
    return result


def _safe_external_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        hostname = parsed.hostname.casefold()
        if "." not in hostname or hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        )
    except ValueError:
        return False


def _risk_sort_key(risk: dict[str, Any]) -> tuple[int, float, str]:
    return (
        _PRIORITY_RANK[risk["priority"]],
        float(risk["related_asset_weight_pct"]),
        risk["last_updated_at"],
    )


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


def _market_groups(category: str, item: NewsItem, portfolio_groups: set[str]) -> List[str]:
    text = _normalize(f"{item.title} {item.summary} {item.reason}")
    groups = set()
    if any(_normalize(keyword) in text for keyword in _COIN_MARKET_KEYWORDS):
        groups.add("coin")
    if any(_normalize(keyword) in text for keyword in _ISA_MARKET_KEYWORDS):
        groups.add("isa")
    if category == "market":
        return sorted(groups & portfolio_groups)
    if any(_normalize(keyword) in text for keyword in _BROAD_FINANCIAL_KEYWORDS):
        groups.update(("coin", "isa"))
    if category in {"rates", "inflation"} and any(_normalize(keyword) in text for keyword in _RATE_MARKET_KEYWORDS):
        groups.update(("coin", "isa"))
    if category == "fx" and any(_normalize(keyword) in text for keyword in _FX_MARKET_KEYWORDS):
        groups.update(("coin", "isa"))
    if category == "regulation" and not groups and any(keyword in text for keyword in ("금융", "거래소", "거래 제한", "거래제한")):
        groups.update(("coin", "isa"))
    return sorted(groups & portfolio_groups)


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
    if article_count >= 3:
        score += 2
        reasons.append(f"반복 기사 {article_count}건 (+2)")
    elif article_count == 2:
        score += 1
        reasons.append("반복 기사 2건 (+1)")
    else:
        reasons.append("반복 기사 1건")
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
