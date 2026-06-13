import re
from typing import Dict, List, Sequence, Set, Tuple

from .config import AssetConfig
from .models import NewsItem

_ASSET_KEYWORDS: Dict[str, List[str]] = {
    "BTC": ["BTC", "비트코인", "Bitcoin"],
    "ETH": ["ETH", "이더리움", "Ethereum"],
    "LINK": ["LINK", "체인링크", "Chainlink", "블록체인 오라클"],
    "AAVE": ["AAVE", "에이브", "DeFi", "디파이"],
    "ARB": ["ARB", "아비트럼", "Arbitrum", "레이어2"],
    "RISE_NASDAQ100": ["나스닥100", "나스닥", "NASDAQ", "Nasdaq 100", "기술주", "빅테크", "미국 증시"],
    "TIGER_SP500": ["S&P500", "S&P 500", "스탠더드앤드푸어스", "미국 증시", "미국 주식"],
    "TIGER_GOLD_FUTURES_H": ["금값", "금 가격", "금 선물", "골드", "gold", "안전자산"],
    "PLUS_HUMANOID_ROBOT": ["휴머노이드", "로봇", "피지컬 AI", "AI 로봇", "인공지능 로봇"],
    "SOL_US_NUCLEAR_SMR": ["SMR", "원전", "원자력", "소형모듈원전"],
    "KODEX_K_REIT_INFRA": ["리츠", "REIT", "부동산", "인프라", "상업용 부동산"],
    "ACE_US10Y_BOND_ACTIVE_H": ["미국 국채", "10년물", "금리", "연준", "채권"],
}

_GENERAL_KEYWORDS = [
    "가상자산", "암호화폐", "부동산", "아파트", "전세", "주택", "금리", "환율", "달러", "물가", "CPI", "연준",
    "국채", "중앙은행", "긴축", "인플레이션", "침체", "고용", "규제", "거래제한", "지정학", "제재", "무역갈등",
    "유동성", "자금유출", "신용위험",
]
_POSITIVE_WORDS = ["상승", "강세", "반등", "호재", "인하", "완화", "승인", "유입", "수혜", "확대", "최고", "증가", "회복", "개선", "돌파", "랠리"]
_NEGATIVE_WORDS = ["하락", "약세", "급락", "악재", "인상", "긴축", "규제", "유출", "우려", "둔화", "침체", "불확실", "압박", "부진", "매물", "불안", "조정"]


def default_news_queries() -> List[str]:
    return [
        "비트코인 이더리움 가상자산",
        "미국 증시 나스닥 S&P500 연준 금리",
        "금 가격 달러 안전자산",
        "원전 SMR 원자력",
        "휴머노이드 로봇 AI",
        "리츠 부동산 금리",
        "미국 국채 10년물 채권",
        "한국 부동산 아파트 전세",
    ]


def risk_news_queries() -> List[str]:
    return default_news_queries() + [
        "금리 국채 중앙은행 긴축",
        "물가 CPI 인플레이션",
        "환율 달러",
        "경기둔화 침체 고용",
        "금융 규제 가상자산 규제 거래제한",
        "지정학 제재 무역갈등",
        "유동성 자금유출 신용위험",
    ]


def analyze_news_items(items: Sequence[NewsItem], assets: Sequence[AssetConfig]) -> List[NewsItem]:
    configured_symbols = {asset.symbol for asset in assets}
    analyzed: List[NewsItem] = []
    for item in items:
        text = f"{item.title} {item.summary}"
        related_assets, matched_asset_keywords = _match_assets(text, configured_symbols)
        matched_general = _match_keywords(text, _GENERAL_KEYWORDS)
        if not related_assets and not matched_general:
            continue
        impact = _estimate_impact(text)
        reason_parts: List[str] = []
        if related_assets:
            reason_parts.append(f"관련 키워드: {_format_matched_keywords(related_assets, matched_asset_keywords)}")
        if matched_general:
            reason_parts.append(f"시장 키워드: {', '.join(sorted(matched_general)[:3])}")
        reason_parts.append(f"방향: {impact}")
        analyzed.append(
            NewsItem(
                title=item.title,
                summary=item.summary,
                source=item.source,
                url=item.url,
                published_at=item.published_at,
                related_assets=related_assets,
                impact=impact,
                reason=" / ".join(reason_parts),
            )
        )
    return analyzed


def _match_assets(text: str, configured_symbols: Set[str]) -> Tuple[List[str], Dict[str, Set[str]]]:
    related: List[str] = []
    matched_by_symbol: Dict[str, Set[str]] = {}
    for symbol in sorted(configured_symbols):
        matched = _match_keywords(text, _ASSET_KEYWORDS.get(symbol, [symbol]))
        if matched:
            related.append(symbol)
            matched_by_symbol[symbol] = matched
    return related, matched_by_symbol


def _match_keywords(text: str, keywords: Sequence[str]) -> Set[str]:
    return {keyword for keyword in keywords if _keyword_in_text(text, keyword)}


def _estimate_impact(text: str) -> str:
    positive = sum(1 for word in _POSITIVE_WORDS if _keyword_in_text(text, word))
    negative = sum(1 for word in _NEGATIVE_WORDS if _keyword_in_text(text, word))
    if positive > negative:
        return "긍정"
    if negative > positive:
        return "부정"
    return "중립"


def _keyword_in_text(text: str, keyword: str) -> bool:
    normalized_text = re.sub(r"\s+", " ", text.lower()).strip()
    normalized_keyword = re.sub(r"\s+", " ", keyword.lower()).strip()
    if re.fullmatch(r"[a-z0-9]+", normalized_keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", normalized_text) is not None
    return normalized_keyword in normalized_text


def _format_matched_keywords(related_assets: Sequence[str], matched_asset_keywords: Dict[str, Set[str]]) -> str:
    formatted: List[str] = []
    for symbol in related_assets:
        for keyword in sorted(matched_asset_keywords.get(symbol, set())):
            if keyword not in formatted:
                formatted.append(keyword)
        if len(formatted) >= 4:
            break
    return ", ".join(formatted)
