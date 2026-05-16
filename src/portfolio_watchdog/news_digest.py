import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .models import NewsItem

_THEME_KEYWORDS = [
    "비트코인",
    "이더리움",
    "알트코인",
    "가상자산",
    "금리",
    "국채",
    "채권",
    "나스닥",
    "S&P",
    "달러",
    "금",
    "리츠",
    "부동산",
    "전세",
    "원전",
    "SMR",
    "로봇",
    "AI",
    "규제",
    "물가",
    "연준",
]
_HIGH_RISK_KEYWORDS = [
    "급락",
    "급등",
    "규제",
    "금리 급등",
    "채권가격 폭락",
    "국채가 급락",
    "물가",
    "CPI",
    "연준",
    "인상",
    "긴축",
    "유출",
    "하락 반전",
    "부진 지속",
]
_IMPACT_RANK = {"부정": 3, "긍정": 2, "중립": 1}


@dataclass
class NewsTopic:
    key: str
    title: str
    impact: str
    items: List[NewsItem]
    related_assets: List[str]
    high_risk_keywords: List[str]


def cluster_news_items(news_items: Sequence[NewsItem]) -> List[NewsTopic]:
    grouped: Dict[str, List[NewsItem]] = {}
    for item in news_items:
        grouped.setdefault(_topic_key(item), []).append(item)

    topics = [_build_topic(key, items) for key, items in grouped.items()]
    topics.sort(key=_topic_sort_key, reverse=True)
    return topics


def build_news_watch_points(topics: Sequence[NewsTopic]) -> List[str]:
    if not topics:
        return ["추가 확인할 주요 뉴스가 없습니다."]

    text = " ".join(topic.title for topic in topics)
    points: List[str] = []
    if _contains_any(text, ["금리", "국채", "채권", "물가", "연준"]):
        points.append("금리/채권 뉴스가 ISA 성장주, 리츠, 국채형 자산으로 번지는지 확인")
    if _contains_any(text, ["비트코인", "이더리움", "알트코인", "가상자산"]):
        points.append("비트코인 회복이 이더리움과 알트코인으로 확산되는지 확인")
    if _contains_any(text, ["달러", "금"]):
        points.append("달러와 금 가격 흐름이 방어 자산 역할을 강화하는지 확인")
    if _contains_any(text, ["부동산", "전세", "리츠"]):
        points.append("부동산/전세 심리가 리츠와 인프라 자산에 주는 압력 확인")
    if _contains_any(text, ["로봇", "AI", "SMR", "원전"]):
        points.append("테마 뉴스가 단기 주가 반응을 넘어 실적 기대까지 이어지는지 확인")
    if not points:
        points.append("동일 이슈의 후속 기사와 가격 반응이 같은 방향인지 확인")
    return points[:4]


def should_create_hourly_codex_source(news_items: Sequence[NewsItem]) -> bool:
    if not news_items:
        return False
    topics = cluster_news_items(news_items)
    negative_count = sum(1 for item in news_items if item.impact == "부정")
    repeated_topic = any(len(topic.items) >= 2 for topic in topics)
    high_risk = any(topic.high_risk_keywords for topic in topics)
    multi_asset = any(len(set(item.related_assets)) >= 2 for item in news_items)
    return negative_count >= 2 or repeated_topic or high_risk or multi_asset


def write_hourly_codex_source(news_items: Sequence[NewsItem], directory: str = "reports", now: Optional[datetime] = None) -> Optional[Path]:
    if not should_create_hourly_codex_source(news_items):
        return None
    generated_at = now or datetime.now()
    path = Path(directory) / f"hourly_news_source_{generated_at:%Y%m%d_%H%M}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_hourly_codex_source(news_items, generated_at), encoding="utf-8")
    return path


def build_hourly_codex_source(news_items: Sequence[NewsItem], generated_at: Optional[datetime] = None) -> str:
    now = generated_at or datetime.now()
    topics = cluster_news_items(news_items)
    lines = [
        "아래 자료를 바탕으로 텔레그램용 1시간 뉴스 고급 요약을 만들어줘.",
        "",
        "[작성 조건]",
        "- 한국어로 10줄 안팎",
        "- 텔레그램 HTML 형식 사용",
        "- 관련 기사 링크 1~3개 포함",
        "- 매수/매도 추천 금지",
        "- 내 포트폴리오에 왜 중요한지 중심으로 작성",
        "- 마지막에 확인 포인트 2~3개 포함",
        "",
        "[기준 시각]",
        f"- {now:%Y-%m-%d %H:%M}",
        "",
        "[토픽 요약]",
    ]
    for index, topic in enumerate(topics[:6], start=1):
        related = ", ".join(topic.related_assets) or "시장 전반"
        risks = ", ".join(topic.high_risk_keywords) or "-"
        lines.extend(
            [
                f"{index}. [{topic.impact}] {topic.title}",
                f"   관련 자산: {related}",
                f"   기사 수: {len(topic.items)}",
                f"   고위험 키워드: {risks}",
            ]
        )
        for item in topic.items[:3]:
            lines.append(f"   - {item.title} / {item.reason or '추가 확인 필요'}")
            if item.url:
                lines.append(f"     링크: {item.url}")
    lines.extend(["", "[확인 포인트]", *[f"- {point}" for point in build_news_watch_points(topics)]])
    return "\n".join(lines)


def _build_topic(key: str, items: List[NewsItem]) -> NewsTopic:
    items = sorted(items, key=lambda item: (_IMPACT_RANK.get(item.impact, 0), item.published_at or datetime.min), reverse=True)
    related_assets = _unique_asset_symbols(items)
    title = _topic_title(items[0])
    high_risk_keywords = _matched_keywords(" ".join(f"{item.title} {item.reason}" for item in items), _HIGH_RISK_KEYWORDS)
    impact = _dominant_impact(items)
    return NewsTopic(key=key, title=title, impact=impact, items=items, related_assets=related_assets, high_risk_keywords=high_risk_keywords)


def _topic_sort_key(topic: NewsTopic) -> tuple:
    return (
        _IMPACT_RANK.get(topic.impact, 0),
        len(topic.high_risk_keywords),
        len(topic.items),
        len(topic.related_assets),
    )


def _topic_key(item: NewsItem) -> str:
    text = f"{item.title} {item.reason}"
    theme = _first_matched_keyword(text, _THEME_KEYWORDS)
    assets = ",".join(sorted(set(item.related_assets[:3])))
    if theme or assets:
        return f"{assets}:{theme}"
    title = _normalize_title(item.title)
    return title[:28] or item.url or item.title


def _topic_title(item: NewsItem) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", item.title).strip()
    return title or item.title


def _dominant_impact(items: Sequence[NewsItem]) -> str:
    counts = {"부정": 0, "긍정": 0, "중립": 0}
    for item in items:
        counts[item.impact if item.impact in counts else "중립"] += 1
    return max(counts, key=lambda impact: (counts[impact], _IMPACT_RANK[impact]))


def _unique_asset_symbols(items: Sequence[NewsItem]) -> List[str]:
    result: List[str] = []
    for item in items:
        for symbol in item.related_assets:
            if symbol not in result:
                result.append(symbol)
    return result


def _normalize_title(value: str) -> str:
    normalized = re.sub(r"\s+-\s+[^-]+$", "", value.lower())
    normalized = re.sub(r"[^0-9a-z가-힣]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _first_matched_keyword(text: str, keywords: Sequence[str]) -> str:
    matched = _matched_keywords(text, keywords)
    return matched[0] if matched else ""


def _matched_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    lowered = text.lower()
    result: List[str] = []
    for keyword in keywords:
        if keyword.lower() in lowered and keyword not in result:
            result.append(keyword)
    return result


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)
